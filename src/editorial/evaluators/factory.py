from __future__ import annotations

from dataclasses import dataclass

from editorial.config.models import ProcessorConfig
from editorial.evaluators.llm_relevance import LLMRelevanceEvaluator
from editorial.evaluators.llm_summary_quality import LLMSummaryQualityEvaluator
from editorial.evaluators.rule_relevance import RuleBasedRelevanceEvaluator
from editorial.interfaces import Evaluator
from editorial.llm import LLMProvider, LLMProviderFactoryConfig, build_llm_provider


@dataclass(frozen=True)
class EvaluatorDescriptor:
    key: str
    display_name: str
    kind: str


def describe_evaluator(config: ProcessorConfig) -> EvaluatorDescriptor:
    if config.type == "rule_relevance":
        evaluator_type = RuleBasedRelevanceEvaluator
        kind = "relevance"
    elif config.type == "llm_relevance":
        evaluator_type = LLMRelevanceEvaluator
        kind = "relevance"
    elif config.type == "llm_summary_quality":
        evaluator_type = LLMSummaryQualityEvaluator
        kind = "summary_quality"
    else:
        raise ValueError(f"Unsupported evaluator type: {config.type!r}")
    return EvaluatorDescriptor(
        key=config.key or evaluator_type.name,
        display_name=config.name or config.key or evaluator_type.name,
        kind=kind,
    )


def build_evaluator(config: ProcessorConfig) -> Evaluator:
    if config.type == "rule_relevance":
        return _with_configured_identity(
            RuleBasedRelevanceEvaluator(
                include=config.settings.get("include", []),
                exclude=config.settings.get("exclude", []),
                weights=config.settings.get("weights", {}),
            ),
            config.key,
            config.name,
        )
    if config.type == "llm_relevance":
        provider = _build_llm_evaluator_provider(config)
        return _with_configured_identity(
            LLMRelevanceEvaluator(
                provider=provider,
                criterion=config.settings.get("criterion", "editorial_relevance"),
            ),
            config.key,
            config.name,
        )
    if config.type == "llm_summary_quality":
        return _with_configured_identity(
            LLMSummaryQualityEvaluator(
                provider=_build_llm_evaluator_provider(config),
                criterion=config.settings.get("criterion", "summary_quality"),
                summary_extractor=config.settings.get(
                    "summary_extractor", "llm_summary"
                ),
            ),
            config.key,
            config.name,
        )
    raise ValueError(f"Unsupported evaluator type: {config.type!r}")


def _with_configured_identity(
    evaluator: Evaluator,
    key: str | None,
    display_name: str | None,
) -> Evaluator:
    identity = key or evaluator.name
    setattr(evaluator, "name", identity)
    setattr(evaluator, "display_name", display_name or identity)
    return evaluator


def _build_llm_evaluator_provider(config: ProcessorConfig) -> LLMProvider:
    provider_config = config.settings.get("provider")
    if isinstance(provider_config, dict):
        settings = provider_config
        provider_type = settings.get("type")
        if provider_type is None:
            raise ValueError(f"{config.type} provider config requires provider.type")
    elif provider_config is None or isinstance(provider_config, str):
        settings = config.settings
        provider_type = provider_config or "fake"
    else:
        raise ValueError(f"{config.type} provider config must be a mapping or string")

    return build_llm_provider(
        LLMProviderFactoryConfig(
            provider=provider_type,
            response_text=settings.get("response_text", "Fake response"),
            model=settings.get("model"),
            api_key_env=settings.get("api_key_env", "OPENAI_API_KEY"),
            base_url=settings.get("base_url"),
            organization=settings.get("organization"),
            project=settings.get("project"),
            temperature=settings.get("temperature"),
            max_tokens=settings.get("max_tokens"),
            metadata=settings.get("metadata", {}),
        )
    )
