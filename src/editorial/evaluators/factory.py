from __future__ import annotations

from editorial.config.models import ProcessorConfig
from editorial.evaluators.rule_relevance import RuleBasedRelevanceEvaluator
from editorial.interfaces import Evaluator


def build_evaluator(config: ProcessorConfig) -> Evaluator:
    if config.type == "rule_relevance":
        return RuleBasedRelevanceEvaluator(
            include=config.settings.get("include", []),
            exclude=config.settings.get("exclude", []),
            weights=config.settings.get("weights", {}),
        )
    raise ValueError(f"Unsupported evaluator type: {config.type!r}")
