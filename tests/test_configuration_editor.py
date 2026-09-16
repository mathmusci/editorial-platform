import pytest
import yaml
from fastapi.testclient import TestClient

from editorial.config import load_publication_config
from editorial.web import create_app
from editorial.web.configuration_editor import Draft


def values(draft):
    result = {}
    for f in draft.fields():
        if f["kind"] == "checkbox":
            if f["value"]:
                result[f["id"]] = "on"
        else:
            result[f["id"]] = "" if f["value"] is None else str(f["value"])
    return result


def test_edit_preserves_unowned_sections_and_secrets(tmp_path):
    source = tmp_path / "publication.yaml"
    raw = {
        "publication": {"name": "Original", "custom": "keep"},
        "providers": [
            {
                "type": "rss",
                "settings": {
                    "url": "https://user:private@example.org/feed",
                    "custom": {"token": "private-token"},
                },
            }
        ],
        "extractors": [
            {
                "type": "llm_summary",
                "provider": {
                    "type": "openai",
                    "model": "some-model",
                    "api_key_env": "MY_API_KEY",
                    "metadata": {"secret": "private-secret"},
                },
            }
        ],
        "evaluators": [
            {
                "type": "rule_relevance",
                "include": ["statistics"],
                "metadata": {"token": "private-eval"},
            }
        ],
        "editorial_policy": {"maximum_articles": 7},
        "optimisation": {"strategy": "greedy", "settings": {"max_articles": 4}},
        "publishers": [{"type": "markdown", "template": "templates/newsletter.md.j2"}],
        "custom_top_level": {"keep": True},
    }
    source.write_text(yaml.safe_dump(raw))
    draft = Draft.open(source)
    form = values(draft)
    assert "private" not in str(form)
    form["publication.name"] = "Edited"
    draft.apply(form)
    draft.save(source, overwrite=True)
    saved = yaml.safe_load(source.read_text())
    for key in (
        "evaluators",
        "editorial_policy",
        "optimisation",
        "publishers",
        "custom_top_level",
    ):
        assert saved[key] == raw[key]
    assert saved["providers"] == raw["providers"]
    assert saved["extractors"][0]["provider"]["metadata"] == {
        "secret": "private-secret"
    }
    assert saved["publication"] == {"name": "Edited", "custom": "keep"}
    assert load_publication_config(source).publication.name == "Edited"


def test_save_as_conflict_and_source_change(tmp_path):
    source = tmp_path / "original.yaml"
    source.write_text("publication:\n  name: Original\n")
    draft = Draft.open(source)
    draft.data["publication"]["name"] = "Copy"
    other = tmp_path / "copy.yaml"
    draft.save(other, overwrite=False)
    assert load_publication_config(source).publication.name == "Original"
    with pytest.raises(FileExistsError):
        draft.save(other, overwrite=False)
    other.write_text("publication:\n  name: External edit\n")
    with pytest.raises(ValueError, match="changed on disk"):
        draft.save(other, overwrite=True)
    assert load_publication_config(other).publication.name == "External edit"


def test_validation_and_numeric_conversion(tmp_path):
    draft = Draft.open(None)
    draft.data["providers"] = [{"type": "rss"}]
    draft.data["extractors"] = [
        {"type": "reading_time", "words_per_minute": "0"},
        {"type": "llm_summary", "provider": {"type": "ollama"}},
    ]
    with pytest.raises(ValueError):
        draft.save(tmp_path / "invalid.yaml", False)
    assert {
        "publication.name",
        "providers.0.url",
        "extractors.0.words_per_minute",
        "extractors.1.provider.model",
    } <= draft.errors.keys()
    assert not (tmp_path / "invalid.yaml").exists()
    form = values(draft)
    form.update(
        {
            "publication.name": "Test",
            "providers.0.url": "https://example.org/feed",
            "extractors.0.words_per_minute": "250",
            "extractors.1.provider.model": "qwen3.5:9b",
            "extractors.1.provider.temperature": "0.2",
            "extractors.1.provider.max_tokens": "200",
        }
    )
    draft.apply(form)
    draft.save(tmp_path / "valid.yaml", False)
    data = yaml.safe_load((tmp_path / "valid.yaml").read_text())
    assert data["extractors"][0]["words_per_minute"] == 250
    assert data["extractors"][1]["provider"]["temperature"] == 0.2
    assert data["extractors"][1]["provider"]["max_tokens"] == 200


def test_static_article_and_legacy_fake_metadata(tmp_path):
    source = tmp_path / "legacy.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "publication": {"name": "Old"},
                "providers": [
                    {
                        "type": "static",
                        "articles": [
                            {
                                "title": "Article",
                                "metadata": {"keep": 1},
                                "authors": ["A", "B"],
                            }
                        ],
                    }
                ],
                "extractors": [
                    {
                        "type": "llm_summary",
                        "model": "fake-old",
                        "response_text": "Original text",
                        "metadata": {"keep": 2},
                    }
                ],
            }
        )
    )
    draft = Draft.open(source)
    form = values(draft)
    form["providers.0.article.0.summary"] = "New summary"
    draft.apply(form)
    draft.save(source, True)
    saved = yaml.safe_load(source.read_text())
    assert saved["providers"][0]["articles"][0]["metadata"] == {"keep": 1}
    assert saved["providers"][0]["articles"][0]["authors"] == ["A", "B"]
    assert saved["extractors"][0]["metadata"] == {"keep": 2}
    assert saved["extractors"][0]["response_text"] == "Original text"


def test_editor_new_save_then_choose_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as client:
        assert (
            client.post("/configuration/editor", data={"new": "1"}).status_code == 403
        )
        page = client.post(
            "/configuration/editor",
            data={"new": "1", "csrf_token": client.app.state.csrf_token},
        )
        assert page.status_code == 200
        url = page.url.path
        form = {
            "csrf_token": client.app.state.csrf_token,
            "revision": "0",
            "publication.name": "New publication",
            "filename": "new.yaml",
            "action": "save",
        }
        page = client.post(url, data=form)
        assert page.status_code == 200
        assert "Activation pending" in page.text
        assert client.app.state.workspace is None
        assert (
            load_publication_config(tmp_path / "new.yaml").publication.name
            == "New publication"
        )
        assert client.post(url, data=form).status_code == 409
        page = client.post(url, data={**form, "revision": "1", "action": "use"})
        assert "Selected configuration" in page.text
        assert "new.yaml" in page.text


def test_editor_add_remove_and_switch_llm_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as client:
        csrf = client.app.state.csrf_token
        page = client.post(
            "/configuration/editor", data={"new": "1", "csrf_token": csrf}
        )
        url = page.url.path
        revision = 0

        def submit(action, **fields):
            nonlocal revision
            page = client.post(
                url,
                data={
                    "csrf_token": csrf,
                    "revision": str(revision),
                    "action": action,
                    **fields,
                },
            )
            revision += 1
            assert page.status_code == 200, page.text
            return page

        submit("add:providers", add_providers="static", **{"publication.name": "Trial"})
        submit("add_article:0", **{"providers.0.enabled": "on"})
        submit(
            "add:extractors",
            add_extractors="llm_summary",
            **{
                "providers.0.enabled": "on",
                "providers.0.article.0.title": "Test article",
            },
        )
        page = submit(
            "update",
            **{
                "providers.0.enabled": "on",
                "extractors.0.enabled": "on",
                "extractors.0.provider.type": "openai",
            },
        )
        assert "API key environment variable" in page.text
        submit(
            "update",
            **{
                "providers.0.enabled": "on",
                "extractors.0.enabled": "on",
                "extractors.0.provider.model": "gpt-4.1-mini",
            },
        )
        submit(
            "remove_article:0:0",
            **{"providers.0.enabled": "on", "extractors.0.enabled": "on"},
        )
        submit(
            "save",
            filename="trial.yaml",
            **{"providers.0.enabled": "on", "extractors.0.enabled": "on"},
        )
        saved = load_publication_config(tmp_path / "trial.yaml")
        assert saved.providers[0].settings["articles"] == []
        assert saved.extractors[0].settings["provider"]["model"] == "gpt-4.1-mini"


def test_editor_never_renders_existing_secrets(tmp_path):
    source = tmp_path / "secret.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "publication": {"name": "Secrets"},
                "providers": [
                    {
                        "type": "rss",
                        "url": "https://example.org/feed?token=secret-value",
                    }
                ],
                "extractors": [
                    {
                        "type": "llm_summary",
                        "provider": {
                            "type": "openai",
                            "model": "example",
                            "api_key": "private-key",
                            "metadata": {"token": "private-meta"},
                        },
                    }
                ],
            }
        )
    )
    with TestClient(create_app()) as client:
        page = client.post(
            "/configuration/editor",
            data={
                "csrf_token": client.app.state.csrf_token,
                "config_path": str(source),
            },
        )
        assert page.status_code == 200
        for secret in ("secret-value", "private-key", "private-meta"):
            assert secret not in page.text
        assert "Stored value retained" in page.text


def test_save_as_preserves_relative_location_and_duplicate_key_validation(tmp_path):
    source = tmp_path / "original.yaml"
    source.write_text("publication:\n  name: Test\n")
    draft = Draft.open(source)
    (tmp_path / "other").mkdir()
    with pytest.raises(ValueError, match="beside"):
        draft.save(tmp_path / "other" / "copy.yaml", False)
    draft.data["extractors"] = [{"type": "reading_time"}, {"type": "reading_time"}]
    with pytest.raises(ValueError):
        draft.validate()
    assert "extractors.1.key" in draft.errors


@pytest.mark.parametrize(
    ("provider", "models"),
    [
        ("ollama", ["qwen3.5:9b", "deepseek-r1:8b", "gpt-oss:20b"]),
        ("openai", ["gpt-4.1-mini"]),
    ],
)
def test_llm_model_choices_are_provider_specific(provider, models):
    draft = Draft.open(None)
    draft.data["extractors"] = [{"type": "llm_summary", "provider": {"type": provider}}]
    model = next(f for f in draft.fields() if f["id"].endswith(".provider.model"))
    assert model["kind"] == "select"
    assert model["choices"] == models


def test_existing_unlisted_model_is_preserved_as_a_choice(tmp_path):
    source = tmp_path / "publication.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "publication": {"name": "Existing"},
                "extractors": [
                    {
                        "type": "llm_summary",
                        "provider": {"type": "ollama", "model": "older-model"},
                    }
                ],
            }
        )
    )
    draft = Draft.open(source)
    model = next(f for f in draft.fields() if f["id"].endswith(".provider.model"))
    assert model["value"] == "older-model"
    assert model["choices"] == [
        "older-model",
        "qwen3.5:9b",
        "deepseek-r1:8b",
        "gpt-oss:20b",
    ]


def test_active_config_save_blocks_actions_until_activation(tmp_path):
    source = tmp_path / "config.yaml"
    source.write_text("publication:\n  name: Original\n")
    db = tmp_path / "db.sqlite"
    with TestClient(create_app(source, db)) as client:
        csrf = client.app.state.csrf_token
        page = client.post("/configuration/editor", data={"csrf_token": csrf})
        url = page.url.path
        client.app.state.workspace.processing.create_run("ingest", source)
        form = {
            "csrf_token": csrf,
            "revision": "0",
            "publication.name": "Changed",
            "filename": "config.yaml",
            "action": "save",
        }
        assert client.post(url, data=form).status_code == 400
        assert load_publication_config(source).publication.name == "Original"
        client.app.state.workspace.processing.interrupt_active_runs()
        assert client.post(url, data={**form, "revision": "1"}).status_code == 200
        assert client.app.state.workspace.config.publication.name == "Original"
        assert (
            client.post(
                "/operations", data={"csrf_token": csrf, "kind": "ingest"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/workspace",
                data={
                    "csrf_token": csrf,
                    "config_path": str(source),
                    "db_path": str(db),
                },
            ).status_code
            == 200
        )
        assert client.app.state.workspace.config.publication.name == "Changed"
        assert not client.app.state.configuration_changed
