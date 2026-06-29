from __future__ import annotations
from pathlib import Path
from editorial.config.models import ProcessorConfig
from editorial.interfaces import Provider
from editorial.providers.rss import RSSProvider
from editorial.providers.static import StaticProvider

def build_provider(config: ProcessorConfig, base_path: str | Path | None = None) -> Provider:
    if config.type == "static":
        return StaticProvider(articles=config.settings.get("articles", []))
    if config.type == "rss":
        return RSSProvider(
            url=config.settings.get("url"),
            path=config.settings.get("path"),
            source=config.settings.get("source"),
            base_path=base_path,
        )
    raise ValueError(f"Unsupported provider type: {config.type!r}")
