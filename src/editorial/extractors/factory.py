from __future__ import annotations

from editorial.config.models import ProcessorConfig
from editorial.extractors.llm_summary import LLMSummaryExtractor
from editorial.interfaces import Extractor
from editorial.extractors.reading_time import ReadingTimeExtractor
from editorial.llm import FakeLLMProvider


def build_extractor(config: ProcessorConfig) -> Extractor:
    if config.type == "reading_time":
        return ReadingTimeExtractor(
            words_per_minute=config.settings.get("words_per_minute", 200)
        )
    if config.type == "llm_summary":
        return LLMSummaryExtractor(
            FakeLLMProvider(
                response_text=config.settings.get("response_text", ""),
                model=config.settings.get("model", "fake-llm"),
            )
        )
    raise ValueError(f"Unsupported extractor type: {config.type!r}")
