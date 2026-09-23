import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from editorial.models import Article
from editorial.storage import SQLiteArticleRepository
from editorial.web import create_app

CONFIG = Path("tests/fixtures/bis/publication.yaml")


def test_create_database_opens_empty_workspace_and_supports_ingest(tmp_path):
    import time

    with TestClient(create_app()) as client:
        form = {
            "csrf_token": client.app.state.csrf_token,
            "config_path": str(CONFIG.resolve()),
            "db_path": "",
            "new_directory": str(tmp_path),
            "filename": "fresh.sqlite",
        }
        assert (
            client.post("/workspace", data={**form, "new_database": "1"}).status_code
            == 200
        )
        assert not (tmp_path / "fresh.sqlite").exists()
        response = client.post("/workspace", data={**form, "create_database": "1"})
        assert response.status_code == 200
        workspace = client.app.state.workspace
        assert workspace.db_path == tmp_path / "fresh.sqlite"
        assert workspace.articles.list() == []
        assert list(tmp_path.glob(".editorial-*")) == []
        assert client.app.state.csrf_token != form["csrf_token"]
        result = client.post(
            "/operations",
            data={"csrf_token": client.app.state.csrf_token, "kind": "ingest"},
        )
        assert result.status_code == 200
        for _ in range(100):
            if not workspace.processing.runs.active():
                break
            time.sleep(0.02)
        assert len(workspace.articles.list()) == 2


def test_create_database_never_overwrites_existing_file(tmp_path):
    db = tmp_path / "existing.sqlite"
    db.write_bytes(b"Keep this file exactly")
    with TestClient(create_app()) as client:
        response = client.post(
            "/workspace",
            data={
                "csrf_token": client.app.state.csrf_token,
                "config_path": str(CONFIG),
                "new_directory": str(tmp_path),
                "filename": db.name,
                "create_database": "1",
            },
        )
        assert response.status_code == 400
        assert "no file was overwritten" in response.text
        assert db.read_bytes() == b"Keep this file exactly"
        assert client.app.state.workspace is None
        assert list(tmp_path.glob(".editorial-*")) == []


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "test.db",
        "../outside.sqlite",
        "/outside.sqlite",
        "nested/test.sqlite",
        "nested\\test.sqlite",
    ],
)
def test_create_database_rejects_invalid_filename(tmp_path, filename):
    from editorial.web.files import create_database

    with pytest.raises(ValueError):
        create_database(str(CONFIG), str(tmp_path), filename)
    assert list(tmp_path.iterdir()) == []


def test_new_database_folder_selection_cancel_and_active_run(tmp_path):
    with TestClient(create_app(CONFIG, tmp_path / "original.sqlite")) as client:
        workspace = client.app.state.workspace
        form = {
            "csrf_token": client.app.state.csrf_token,
            "config_path": str(CONFIG),
            "db_path": str(workspace.db_path),
            "filename": "fresh.sqlite",
            "new_directory": str(tmp_path),
            "creating": "1",
        }
        page = client.post("/workspace", data={**form, "browse": "db_path"})
        assert "Use this folder" in page.text
        assert 'name="selected_file"' not in page.text
        page = client.post("/workspace", data={**form, "use_folder": str(tmp_path)})
        assert 'value="fresh.sqlite"' in page.text
        assert (
            client.post("/workspace", data={**form, "cancel_creation": "1"}).status_code
            == 200
        )
        assert client.app.state.workspace is workspace
        assert not (tmp_path / "fresh.sqlite").exists()
        workspace.processing.create_run("ingest", CONFIG)
        assert (
            client.post("/workspace", data={**form, "create_database": "1"}).status_code
            == 409
        )
        assert not (tmp_path / "fresh.sqlite").exists()


def test_new_database_requires_valid_config_and_csrf(tmp_path):
    with TestClient(create_app()) as client:
        form = {
            "create_database": "1",
            "filename": "fresh.sqlite",
            "new_directory": str(tmp_path),
            "config_path": "missing.yaml",
        }
        assert client.post("/workspace", data=form).status_code == 403
        assert (
            client.post(
                "/workspace", data={**form, "csrf_token": client.app.state.csrf_token}
            ).status_code
            == 400
        )
        assert list(tmp_path.iterdir()) == []


def test_file_picker_extension_filters(tmp_path):
    from editorial.web.files import file_browser, selected_file

    for name in (
        "config.yaml",
        "config.yml",
        "config.json",
        "data.sqlite",
        "data.sqlite3",
        "data.db",
        "data.db3",
        "notes.txt",
    ):
        (tmp_path / name).touch()
    (tmp_path / "folder").mkdir()
    assert [p.name for p in file_browser("config_path", str(tmp_path))["files"]] == [
        "config.yaml",
        "config.yml",
    ]
    assert [p.name for p in file_browser("db_path", str(tmp_path))["files"]] == [
        "data.sqlite"
    ]
    for name in ("data.db", "data.db3", "data.sqlite3"):
        with pytest.raises(ValueError):
            selected_file("db_path", str(tmp_path / name))


def test_workspace_displays_deployment_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text("publication:\n  name: Relative workspace\n")
    db = tmp_path / "data.sqlite"
    with TestClient(create_app(config, db)) as client:
        page = client.get("/workspace").text
        assert (
            '<output aria-label="Selected configuration">config.yaml</output>' in page
        )
        assert '<output aria-label="Selected database">data.sqlite</output>' in page
        page = client.get("/configuration").text
        assert "<dd>config.yaml</dd>" in page
        assert "<dd>data.sqlite</dd>" in page
        assert 'title="data.sqlite"' in page
        assert str(tmp_path) not in page
        page = client.post(
            "/workspace",
            data={
                "csrf_token": client.app.state.csrf_token,
                "browse": "config_path",
            },
        ).text
        assert '<p class="file-browser-location">.</p>' in page
        relative = client.app.state.workspace.config_path.parent.parent
        page = client.post(
            "/workspace",
            data={
                "csrf_token": client.app.state.csrf_token,
                "field": "config_path",
                "directory": str(relative),
            },
        ).text
        assert '<p class="file-browser-location">..</p>' in page


def test_file_picker_browses_filters_selects_and_preserves_other_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "nested & files"
    folder.mkdir()
    config = folder / "publication.yml"
    config.write_text("publication:\n  name: Selected publication\n")
    db = tmp_path / "chosen.sqlite"
    SQLiteArticleRepository(db)
    (tmp_path / "irrelevant.txt").write_text("hidden from picker")
    with TestClient(create_app()) as client:
        form = {
            "csrf_token": client.app.state.csrf_token,
            "config_path": "",
            "db_path": str(db),
        }
        page = client.post("/workspace", data={**form, "browse": "config_path"})
        assert page.status_code == 200
        assert "nested &amp; files" in page.text
        assert "irrelevant.txt" not in page.text
        assert 'name="selected_file"' not in page.text
        page = client.post(
            "/workspace",
            data={**form, "field": "config_path", "directory": str(folder)},
        )
        assert "publication.yml" in page.text
        page = client.post(
            "/workspace",
            data={**form, "field": "config_path", "selected_file": str(config)},
        )
        assert page.status_code == 200
        assert (
            'name="config_path" value="' + str(config).replace("&", "&amp;") + '"'
            in page.text
        )
        assert str(db) in page.text
        assert client.app.state.workspace is None
        form["config_path"] = str(config)
        page = client.post("/workspace", data={**form, "browse": "db_path"})
        assert 'name="selected_file" value="' + str(db) + '"' in page.text
        assert "irrelevant.txt" not in page.text
        page = client.post("/workspace", data={**form, "cancel_browser": "1"})
        assert page.status_code == 200
        assert str(db) in page.text
        assert client.app.state.workspace is None
        assert client.post("/workspace", data=form).status_code == 200
        assert client.app.state.workspace.config_path == config
        assert client.app.state.workspace.db_path == db


@pytest.mark.parametrize(
    "action",
    [
        {"browse": "unknown"},
        {"field": "config_path", "directory": "/this-directory-does-not-exist"},
        {"field": "config_path", "selected_file": "/this-file-does-not-exist.yaml"},
    ],
)
def test_file_picker_invalid_requests_and_csrf(action):
    with TestClient(create_app()) as client:
        assert client.post("/workspace", data=action).status_code == 403
        response = client.post(
            "/workspace",
            data={
                **action,
                "csrf_token": client.app.state.csrf_token,
            },
        )
        assert response.status_code == 400
        assert "Cannot browse" in response.text
        assert client.app.state.workspace is None


def test_file_picker_rejects_wrong_file_type_and_directory(tmp_path):
    from editorial.web.files import file_browser, selected_file

    wrong = tmp_path / "other.txt"
    wrong.write_text("not a configuration")
    for path in (wrong, tmp_path):
        with pytest.raises(ValueError):
            selected_file("config_path", str(path))
    with pytest.raises(ValueError):
        file_browser("config_path", str(wrong))
    assert file_browser("db_path", str(tmp_path))["files"] == []


def test_start_without_files_then_open_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as client:
        assert client.app.state.workspace is None
        for path in ("/", "/articles", "/operations", "/configuration", "/proposals"):
            page = client.get(path)
            assert page.status_code == 200
            assert page.url.path == "/workspace"
            assert "<h1>Open workspace</h1>" in page.text
            assert 'aria-label="Workspace"' not in page.text
        assert client.get("/static/workspace.css").status_code == 200
        assert client.post("/operations", data={"kind": "ingest"}).status_code == 409
        assert list(tmp_path.iterdir()) == []
        config = tmp_path / "publication.yaml"
        config.write_text("publication:\n  name: Newly opened\n")
        db = tmp_path / "new.sqlite"
        token = client.app.state.csrf_token
        form = {"csrf_token": token, "config_path": str(config), "db_path": str(db)}
        assert client.post("/workspace", data=form).status_code == 400
        assert not db.exists()
        assert client.app.state.workspace is None
        SQLiteArticleRepository(db)
        page = client.post("/workspace", data=form)
        assert page.status_code == 200
        assert "Newly opened" in page.text
        assert 'aria-label="Workspace"' in page.text
        assert client.app.state.workspace.db_path == db
        assert client.app.state.csrf_token != token


def test_database_only_prefills_selection_without_creating_file(tmp_path):
    db = tmp_path / "not-created.sqlite"
    with TestClient(create_app(db_path=db)) as client:
        assert str(db) in client.get("/workspace").text
        assert client.app.state.workspace is None
        assert not db.exists()


def test_web_cli_without_config_and_config_only_default(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from editorial.cli import app

    config = CONFIG.resolve()
    monkeypatch.chdir(tmp_path)
    launched = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: launched.append(app))
    result = CliRunner().invoke(app, ["web"])
    assert result.exit_code == 0
    assert launched[-1].state.workspace is None
    assert not (tmp_path / "editorial.sqlite").exists()
    result = CliRunner().invoke(app, ["web", "--config", str(config)])
    assert result.exit_code == 0
    assert launched[-1].state.workspace.db_path == Path("editorial.sqlite")
    launched[-1].state.workspace.coordinator.shutdown()


def test_switch_workspace_updates_reads_writes_and_invalidates_old_forms(tmp_path):
    original = tmp_path / "original.sqlite"
    target = tmp_path / "target.sqlite"
    article = Article(title="Only in target")
    SQLiteArticleRepository(target).insert(article)
    config = tmp_path / "other.yaml"
    config.write_text(
        "publication:\n  name: Other publication\noptimisation:\n  strategy: greedy\n"
    )
    with TestClient(create_app(CONFIG, original)) as client:
        old_token = client.app.state.csrf_token
        response = client.post(
            "/workspace",
            data={
                "csrf_token": old_token,
                "config_path": str(config),
                "db_path": str(target),
            },
        )
        assert response.status_code == 200
        assert "Other publication" in response.text
        assert str(target) in response.text
        assert client.app.state.workspace.db_path == target
        assert "Only in target" in client.get("/articles").text
        assert (
            client.post(
                "/proposals/generate", data={"csrf_token": old_token}
            ).status_code
            == 403
        )
        result = client.post(
            "/proposals/generate",
            data={
                "csrf_token": client.app.state.csrf_token,
            },
        )
        assert result.status_code == 200
        with sqlite3.connect(target) as connection:
            assert (
                connection.execute("SELECT count(*) FROM issue_proposals").fetchone()[0]
                == 1
            )
        with sqlite3.connect(original) as connection:
            assert (
                connection.execute("SELECT count(*) FROM issue_proposals").fetchone()[0]
                == 0
            )


@pytest.mark.parametrize(
    "invalid",
    ["missing", "directory", "text", "other_sqlite", "config", "scalar_config"],
)
def test_invalid_selection_preserves_current_workspace(tmp_path, invalid):
    original = tmp_path / "original.sqlite"
    target = tmp_path / "target.sqlite"
    config = CONFIG
    if invalid == "directory":
        target.mkdir()
    elif invalid == "text":
        target.write_text("Not SQLite")
    elif invalid == "other_sqlite":
        with sqlite3.connect(target) as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
    elif invalid in {"config", "scalar_config"}:
        SQLiteArticleRepository(target)
        config = tmp_path / "invalid.yaml"
        config.write_text(
            "publication: [broken" if invalid == "config" else "not a mapping"
        )
    with TestClient(create_app(CONFIG, original)) as client:
        old = client.app.state.workspace
        token = client.app.state.csrf_token
        response = client.post(
            "/workspace",
            data={
                "csrf_token": token,
                "config_path": str(config),
                "db_path": str(target),
            },
        )
        assert response.status_code == 400
        assert "Cannot open workspace" in response.text
        assert client.app.state.workspace is old
        assert client.app.state.csrf_token == token
        if invalid == "missing":
            assert not target.exists()
        if invalid == "other_sqlite":
            with sqlite3.connect(target) as connection:
                assert connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall() == [("unrelated",)]


@pytest.mark.parametrize("active_target", [False, True])
def test_selection_rejects_active_processing_runs(tmp_path, active_target):
    from editorial.processing import ProcessingRunService

    original = tmp_path / "original.sqlite"
    target = tmp_path / "target.sqlite"
    SQLiteArticleRepository(target)
    with TestClient(create_app(CONFIG, original)) as client:
        active_db = target if active_target else original
        service = ProcessingRunService(active_db)
        run = service.create_run("ingest", CONFIG)
        response = client.post(
            "/workspace",
            data={
                "csrf_token": client.app.state.csrf_token,
                "config_path": str(CONFIG),
                "db_path": str(target),
            },
        )
        assert response.status_code == (400 if active_target else 409)
        assert client.app.state.workspace.db_path == original
        assert service.runs.get(run.id).status == "queued"


def test_workspace_selection_requires_csrf_and_shows_current_paths(tmp_path):
    db = tmp_path / "workspace.sqlite"
    with TestClient(create_app(CONFIG, db)) as client:
        workspace_page = client.get("/configuration")
        assert 'href="/workspace"' in workspace_page.text
        assert "Change workspace" in workspace_page.text
        assert "Configuration" in workspace_page.text
        assert "Database" in workspace_page.text
        assert str(CONFIG) in workspace_page.text
        assert db.name in workspace_page.text

        page = client.get("/workspace")
        assert page.status_code == 200
        assert "The current workspace remains active" in page.text
        assert str(CONFIG.resolve()) in page.text
        assert str(db) in page.text
        assert client.post("/workspace", data={}).status_code == 403
