from __future__ import annotations

from editorial.config.models import ProcessorConfig
from editorial.interfaces import Extractor
from editorial.extractors.reading_time import ReadingTimeExtractor


def build_extractor(config: ProcessorConfig) -> Extractor:
    if config.type == "reading_time":
        return ReadingTimeExtractor(
            words_per_minute=config.settings.get("words_per_minute", 200)
        )
    raise ValueError(f"Unsupported extractor type: {config.type!r}")
