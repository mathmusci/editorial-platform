from __future__ import annotations

from editorial.config.models import ProcessorConfig
from editorial.extractors.llm_summary import LLMSummaryExtractor
from editorial.interfaces import Extractor
from editorial.extractors.reading_time import ReadingTimeExtractor
from editorial.llm import LLMProviderFactoryConfig, build_llm_provider


def build_extractor(config: ProcessorConfig) -> Extractor:
    if config.type == "reading_time":
        return ReadingTimeExtractor(
            words_per_minute=config.settings.get("words_per_minute", 200)
        )
    if config.type == "llm_summary":
        return LLMSummaryExtractor(_build_llm_summary_provider(config))
    raise ValueError(f"Unsupported extractor type: {config.type!r}")


def _build_llm_summary_provider(config: ProcessorConfig):
    provider_config = config.settings.get("provider")
    if provider_config is None:
        return build_llm_provider(
            LLMProviderFactoryConfig(
                provider="fake",
                response_text=config.settings.get("response_text", ""),
                model=config.settings.get("model", "fake-llm"),
                metadata=config.settings.get("metadata", {}),
            )
        )
    if not isinstance(provider_config, dict):
        raise ValueError("llm_summary provider config must be a mapping")

    provider_type = provider_config.get("type")
    if provider_type is None:
        raise ValueError("llm_summary provider config requires provider.type")

    return build_llm_provider(
        LLMProviderFactoryConfig(
            provider=provider_type,
            response_text=provider_config.get("response_text", ""),
            model=provider_config.get("model"),
            api_key_env=provider_config.get("api_key_env", "OPENAI_API_KEY"),
            base_url=provider_config.get("base_url"),
            organization=provider_config.get("organization"),
            project=provider_config.get("project"),
            temperature=provider_config.get("temperature", 0),
            max_tokens=provider_config.get("max_tokens", 180),
            metadata=provider_config.get("metadata", {}),
        )
    )
