from __future__ import annotations

import json
from typing import Any

from editorial.llm import LLMProvider
from editorial.models import Article, Evaluation, Extraction
from editorial.prompts import RELEVANCE_PROMPT_VERSION, build_relevance_prompt


class LLMRelevanceEvaluator:
    name = "llm_relevance"
    version = "0.1.0"

    def __init__(self, provider: LLMProvider, criterion: str = "editorial_relevance"):
        self.provider = provider
        self.criterion = criterion

    def evaluate(self, article: Article, extractions: list[Extraction]) -> Evaluation:
        prompt = build_relevance_prompt(article, extractions)
        response = self.provider.generate(prompt)
        parsed = _parse_relevance_response(response.content)
        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="relevance",
            criterion=self.criterion,
            score=parsed["score"],
            confidence=parsed["confidence"],
            rationale=parsed["rationale"],
            payload={
                "raw_response": response.content,
                "metadata": {
                    "generated_by": "llm",
                    "provider": self.provider.name,
                    "model": response.model,
                    "prompt_version": RELEVANCE_PROMPT_VERSION,
                },
            },
        )


def _parse_relevance_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM relevance response must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM relevance response must be a JSON object")

    score = parsed.get("score")
    confidence = parsed.get("confidence")
    rationale = parsed.get("rationale")
    if not _is_number(score) or not 0 <= score <= 100:
        raise ValueError("LLM relevance response score must be a number from 0 to 100")
    if not _is_number(confidence) or not 0 <= confidence <= 1:
        raise ValueError(
            "LLM relevance response confidence must be a number from 0 to 1"
        )
    if not isinstance(rationale, str) or not rationale:
        raise ValueError("LLM relevance response rationale must be a non-empty string")

    return {
        "score": float(score),
        "confidence": float(confidence),
        "rationale": rationale,
    }


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
