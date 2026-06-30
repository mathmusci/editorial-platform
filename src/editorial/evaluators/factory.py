from __future__ import annotations

from editorial.config.models import ProcessorConfig
from editorial.evaluators.llm_relevance import LLMRelevanceEvaluator
from editorial.evaluators.rule_relevance import RuleBasedRelevanceEvaluator
from editorial.interfaces import Evaluator
from editorial.llm import LLMProviderFactoryConfig, build_llm_provider


def build_evaluator(config: ProcessorConfig) -> Evaluator:
    if config.type == "rule_relevance":
        return RuleBasedRelevanceEvaluator(
            include=config.settings.get("include", []),
            exclude=config.settings.get("exclude", []),
            weights=config.settings.get("weights", {}),
        )
    if config.type == "llm_relevance":
        provider = build_llm_provider(
            LLMProviderFactoryConfig(
                provider=config.settings.get("provider", "fake"),
                response_text=config.settings.get("response_text", "Fake response"),
                model=config.settings.get("model"),
                api_key_env=config.settings.get("api_key_env", "OPENAI_API_KEY"),
                base_url=config.settings.get("base_url"),
                organization=config.settings.get("organization"),
                project=config.settings.get("project"),
                metadata=config.settings.get("metadata", {}),
            )
        )
        return LLMRelevanceEvaluator(
            provider=provider,
            criterion=config.settings.get("criterion", "editorial_relevance"),
        )
    raise ValueError(f"Unsupported evaluator type: {config.type!r}")
