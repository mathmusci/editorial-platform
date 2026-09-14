from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from editorial.config import load_publication_config
from editorial.config.models import ProcessorConfig
from editorial.models import Article


TYPES = {
    "providers": {"rss": "RSS feed", "static": "Static articles"},
    "extractors": {"reading_time": "Reading time", "llm_summary": "LLM summary"},
}
LLM_MODELS = {
    "ollama": ["qwen3.5:9b", "deepseek-r1:8b", "gpt-oss:20b"],
    "openai": ["gpt-4.1-mini"],
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settings(entry: dict) -> dict:
    return {
        **(entry.get("settings") or {}),
        **{
            k: v
            for k, v in entry.items()
            if k not in {"type", "key", "name", "enabled", "settings"}
        },
    }


def set_setting(entry: dict, key: str, value: Any) -> None:
    target = (
        entry.get("settings", {}) if key not in entry and "settings" in entry else entry
    )
    target.pop(key, None)
    if value is not None:
        target[key] = value
    if target is entry and isinstance(entry.get("settings"), dict):
        entry["settings"].pop(key, None)


def sensitive(value: Any) -> bool:
    # URLs can contain credentials even when their field name is innocuous.
    if not isinstance(value, str) or "://" not in value:
        return False
    try:
        url = urlsplit(value)
        return bool(url.username or url.password or url.query)
    except ValueError:
        return True


@dataclass
class Draft:
    data: dict
    source: Path | None = None
    original_digest: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    filename: str = "publication.yaml"

    @classmethod
    def open(cls, path: Path | None) -> Draft:
        if path is None:
            return cls(
                {
                    "publication": {"name": "", "description": ""},
                    "providers": [],
                    "extractors": [],
                }
            )
        path = path.resolve(strict=True)
        load_publication_config(path)
        raw = yaml.safe_load(path.read_text())
        return cls(raw, path, digest(path), filename=path.name)

    def fields(self) -> list[dict]:
        result = []

        def add(id, label, obj, key, kind="text", default="", choices=None):
            value = obj.get(key, default)
            hidden = sensitive(value)
            result.append(
                dict(
                    id=id,
                    label=label,
                    obj=obj,
                    key=key,
                    kind=kind,
                    value="" if hidden else value,
                    protected=hidden,
                    choices=choices,
                )
            )

        publication = self.data.setdefault("publication", {})
        add("publication.name", "Publication name", publication, "name")
        add(
            "publication.description",
            "Description",
            publication,
            "description",
            "textarea",
        )
        for group in TYPES:
            for i, entry in enumerate(self.data.get(group, [])):
                prefix = f"{group}.{i}"
                if entry["type"] not in TYPES[group]:
                    continue
                for key, label, kind in [
                    ("name", "Display name", "text"),
                    ("key", "Processor key", "text"),
                    ("enabled", "Enabled", "checkbox"),
                ]:
                    add(
                        f"{prefix}.{key}",
                        label,
                        entry,
                        key,
                        kind,
                        True if key == "enabled" else "",
                    )
                config = settings(entry)
                if entry["type"] == "rss":
                    for key, label in [
                        ("url", "Feed URL"),
                        ("path", "Local feed path"),
                        ("source", "Source name"),
                    ]:
                        add(f"{prefix}.{key}", label, config, key)
                elif entry["type"] == "static":
                    for j, article in enumerate(config.get("articles", [])):
                        for key, label in [
                            ("title", "Title"),
                            ("url", "URL"),
                            ("source", "Source"),
                            ("published_at", "Published at"),
                            ("authors", "Authors (one per line)"),
                            ("summary", "Summary"),
                            ("content", "Content"),
                        ]:
                            add(
                                f"{prefix}.article.{j}.{key}",
                                label,
                                article,
                                key,
                                "textarea"
                                if key in {"authors", "summary", "content"}
                                else "text",
                            )
                            if key == "authors":
                                result[-1]["value"] = "\n".join(
                                    article.get("authors", [])
                                )
                elif entry["type"] == "reading_time":
                    add(
                        f"{prefix}.words_per_minute",
                        "Words per minute",
                        config,
                        "words_per_minute",
                        "number",
                        200,
                    )
                elif entry["type"] == "llm_summary":
                    provider = config.get("provider") or {
                        "type": "fake",
                        **{
                            k: config[k]
                            for k in ("model", "response_text", "metadata")
                            if k in config
                        },
                    }
                    add(
                        f"{prefix}.provider.type",
                        "LLM provider",
                        provider,
                        "type",
                        "select",
                        "fake",
                        ["fake", "openai", "ollama"],
                    )
                    for key, label, kind, default in [
                        ("model", "Model", "text", ""),
                        ("base_url", "Base URL", "text", ""),
                        ("temperature", "Temperature", "number", 0),
                        ("max_tokens", "Maximum tokens", "number", 180),
                        (
                            "api_key_env",
                            "API key environment variable",
                            "text",
                            "OPENAI_API_KEY",
                        ),
                        ("organization", "Organisation", "text", ""),
                        ("project", "Project", "text", ""),
                        ("response_text", "Fake response", "textarea", ""),
                    ]:
                        if (
                            key in {"base_url", "temperature", "max_tokens"}
                            and provider["type"] == "fake"
                        ):
                            continue
                        if (
                            key in {"api_key_env", "organization", "project"}
                            and provider["type"] != "openai"
                        ):
                            continue
                        if key == "response_text" and provider["type"] != "fake":
                            continue
                        choices = None
                        if key == "model" and provider["type"] in LLM_MODELS:
                            kind = "select"
                            choices = list(LLM_MODELS[provider["type"]])
                            existing_model = provider.get("model")
                            if existing_model and existing_model not in choices:
                                choices.insert(0, existing_model)
                        add(
                            f"{prefix}.provider.{key}",
                            label,
                            provider,
                            key,
                            kind,
                            default,
                            choices,
                        )
        return result

    def apply(self, form: dict[str, str]) -> None:
        for f in self.fields():
            key = f["id"]
            if key not in form and f["kind"] != "checkbox":
                continue
            value: Any = form.get(key, "")
            if f["protected"] and not value:
                continue
            if f["kind"] == "checkbox":
                value = key in form
            if value == f["value"] or (value == "" and f["value"] is None):
                continue
            parts = key.split(".")
            if parts[0] == "publication":
                self.data["publication"][parts[1]] = value
                continue
            entry = self.data[parts[0]][int(parts[1])]
            if parts[2] in {"key", "name", "enabled"}:
                if value == "":
                    entry.pop(parts[2], None)
                else:
                    entry[parts[2]] = value
            elif parts[2] == "article":
                article = settings(entry)["articles"][int(parts[3])]
                if parts[4] == "authors":
                    value = [s.strip() for s in value.splitlines() if s.strip()]
                if value == "" and parts[4] != "title":
                    article.pop(parts[4], None)
                else:
                    article[parts[4]] = value
            elif parts[2] == "provider":
                existing = settings(entry)
                provider = copy.deepcopy(
                    existing.get("provider")
                    or {
                        "type": "fake",
                        **{
                            k: existing[k]
                            for k in ("model", "response_text", "metadata")
                            if k in existing
                        },
                    }
                )
                if value == "":
                    provider.pop(parts[3], None)
                else:
                    provider[parts[3]] = value
                set_setting(entry, "provider", provider)
            else:
                set_setting(entry, parts[2], None if value == "" else value)
        self.revision += 1

    def validate(self) -> dict:
        data = copy.deepcopy(self.data)
        self.errors = {}
        if not str(data["publication"].get("name", "")).strip():
            self.errors["publication.name"] = "Enter a publication name."
        for group in TYPES:
            identities = set()
            for i, entry in enumerate(data.get(group, [])):
                prefix = f"{group}.{i}"
                if entry["type"] not in TYPES[group]:
                    continue
                try:
                    ProcessorConfig.model_validate(entry)
                except ValueError:
                    self.errors[prefix + ".key"] = (
                        "Use letters, numbers, underscores or hyphens; start with a letter or number."
                    )
                identity = entry.get("key") or entry["type"]
                if group == "extractors" and entry.get("enabled", True):
                    if identity in identities:
                        self.errors[prefix + ".key"] = (
                            "Give each enabled extractor a unique key."
                        )
                    identities.add(identity)
                config = settings(entry)
                if entry["type"] == "rss" and config.get("url"):
                    try:
                        url = urlsplit(config["url"])
                        if url.scheme not in {"http", "https"} or not url.hostname:
                            raise ValueError
                    except ValueError:
                        self.errors[prefix + ".url"] = (
                            "Enter an HTTP or HTTPS feed URL."
                        )
                if entry["type"] == "rss" and not (
                    config.get("url") or config.get("path")
                ):
                    self.errors[prefix + ".url"] = (
                        "Enter a feed URL or local feed path."
                    )
                if entry["type"] == "static":
                    for j, article in enumerate(config.get("articles", [])):
                        try:
                            Article.model_validate(article)
                        except ValueError:
                            self.errors[f"{prefix}.article.{j}.title"] = (
                                "Check the article title, URL and published date."
                            )
                numbers = (
                    [(config, "words_per_minute", prefix, int)]
                    if entry["type"] == "reading_time"
                    else []
                )
                if entry["type"] == "llm_summary":
                    provider = config.get("provider", {"type": "fake"})
                    if provider.get("type") not in {"fake", "openai", "ollama"}:
                        self.errors[prefix + ".provider.type"] = (
                            "Choose a supported LLM provider."
                        )
                    if (
                        provider.get("type") != "fake"
                        and not str(provider.get("model", "")).strip()
                    ):
                        self.errors[prefix + ".provider.model"] = "Enter a model name."
                    numbers = [
                        (provider, key, prefix + ".provider", cast)
                        for key, cast in [("temperature", float), ("max_tokens", int)]
                    ]
                for obj, key, location, cast in numbers:
                    if key not in obj or obj[key] is None:
                        continue
                    try:
                        number = cast(obj[key])
                        if (
                            number < 0
                            or (key != "temperature" and number == 0)
                            or str(number) in {"nan", "inf", "-inf"}
                        ):
                            raise ValueError
                        obj[key] = number
                        if entry["type"] == "reading_time":
                            set_setting(entry, key, number)
                    except (ValueError, TypeError):
                        self.errors[f"{location}.{key}"] = (
                            "Enter a valid positive number."
                            if key != "temperature"
                            else "Enter a finite number of zero or greater."
                        )
        if self.errors:
            raise ValueError("Check the highlighted fields.")
        return data

    def save(self, destination: Path, overwrite: bool) -> None:
        data = self.validate()
        destination = destination.expanduser().absolute()
        if destination.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("Use a .yaml or .yml filename.")
        if self.source and destination.parent.resolve() != self.source.parent:
            raise ValueError(
                "Save copies beside the original configuration to preserve relative resource paths."
            )
        if overwrite and (
            destination.resolve() != self.source
            or digest(self.source) != self.original_digest
        ):
            raise ValueError("The file changed on disk. Reopen it before saving.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=destination.parent, suffix=".yaml", delete=False
            ) as stream:
                temporary = Path(stream.name)
                yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)
            load_publication_config(temporary)
            if overwrite:
                os.chmod(temporary, self.source.stat().st_mode & 0o777)
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        self.source = destination.resolve()
        self.original_digest = digest(self.source)
        self.data = data
        self.filename = destination.name

    def context(self) -> dict:
        fields = self.fields()
        return {
            "fields": fields,
            "groups": TYPES,
            "entries": {
                group: [
                    {
                        "type": entry["type"],
                        "index": i,
                        "fields": [
                            f for f in fields if f["id"].startswith(f"{group}.{i}.")
                        ],
                    }
                    for i, entry in enumerate(self.data.get(group, []))
                ]
                for group in TYPES
            },
            "draft": self,
        }
