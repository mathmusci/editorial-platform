from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from editorial.config.models import PublicationConfig


def _normalise_processor(entry: dict[str, Any]) -> dict[str, Any]:
    known = {"type", "key", "name", "enabled", "settings"}
    settings = dict(entry.get("settings") or {})
    for key, value in entry.items():
        if key not in known:
            settings[key] = value
    return {
        "type": entry["type"],
        "key": entry.get("key"),
        "name": entry.get("name"),
        "enabled": entry.get("enabled", True),
        "settings": settings,
    }


def _normalise_processors(data: dict[str, Any], key: str) -> None:
    data[key] = [_normalise_processor(item) for item in data.get(key, [])]


def load_publication_config(path: str | Path) -> PublicationConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    for key in ["providers", "extractors", "evaluators", "publishers"]:
        _normalise_processors(raw, key)
    config = PublicationConfig.model_validate(raw)
    config.base_path = config_path.parent
    return config
