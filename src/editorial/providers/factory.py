from __future__ import annotations
from editorial.config.models import ProcessorConfig
from editorial.interfaces import Provider
from editorial.providers.static import StaticProvider

def build_provider(config: ProcessorConfig) -> Provider:
    if config.type == "static":
        return StaticProvider(articles=config.settings.get("articles", []))
    raise ValueError(f"Unsupported provider type: {config.type!r}")
