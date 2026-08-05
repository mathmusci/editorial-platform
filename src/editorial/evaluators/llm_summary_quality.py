from __future__ import annotations

import json
from typing import Any

from editorial.llm import LLMProvider
from editorial.models import Article, Evaluation, Extraction
from editorial.prompts import (
    SUMMARY_QUALITY_PROMPT_VERSION,
    build_summary_quality_prompt,
)


SUMMARY_QUALITY_DIMENSIONS = (
    "faithfulness",
    "coverage",
    "clarity",
    "concision",
)


class LLMSummaryQualityEvaluator:
    name = "llm_summary_quality"
    version = "0.1.0"

    def __init__(
        self,
        provider: LLMProvider,
        criterion: str = "summary_quality",
        summary_extractor: str = "llm_summary",
    ):
        self.provider = provider
        self.criterion = criterion
        self.summary_extractor = summary_extractor

    def evaluate(self, article: Article, extractions: list[Extraction]) -> Evaluation:
        extraction, summary = self._summary_for(article, extractions)
        response = self.provider.generate(
            build_summary_quality_prompt(article, summary)
        )
        parsed = _parse_summary_quality_response(response.content)
        dimensions = {
            dimension: parsed[dimension] for dimension in SUMMARY_QUALITY_DIMENSIONS
        }
        score = round(sum(dimensions.values()) / len(dimensions), 2)
        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="summary_quality",
            criterion=self.criterion,
            score=score,
            confidence=parsed["confidence"],
            rationale=parsed["rationale"],
            payload={
                "dimensions": dimensions,
                "evidence": parsed["evidence"],
                "issues": parsed["issues"],
                "summary_extraction_id": str(extraction.id),
                "summary_extractor": extraction.extractor,
                "raw_response": response.content,
                "metadata": {
                    "generated_by": "llm",
                    "provider": self.provider.name,
                    "model": response.model,
                    "prompt_version": SUMMARY_QUALITY_PROMPT_VERSION,
                },
            },
        )

    def _summary_for(
        self, article: Article, extractions: list[Extraction]
    ) -> tuple[Extraction, str]:
        extraction = next(
            (
                item
                for item in extractions
                if item.kind == "summary" and item.extractor == self.summary_extractor
            ),
            None,
        )
        if extraction is None:
            raise ValueError(
                "Summary quality evaluation requires a summary extraction from "
                f"{self.summary_extractor!r} for article {article.id}"
            )
        summary = extraction.payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(
                "Summary quality evaluation requires a non-empty summary from "
                f"{self.summary_extractor!r} for article {article.id}"
            )
        return extraction, summary


def _parse_summary_quality_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM summary-quality response must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM summary-quality response must be a JSON object")

    for dimension in SUMMARY_QUALITY_DIMENSIONS:
        value = parsed.get(dimension)
        if not _is_number(value) or not 0 <= value <= 100:
            raise ValueError(
                f"LLM summary-quality response {dimension} must be a number "
                "from 0 to 100"
            )
    confidence = parsed.get("confidence")
    if not _is_number(confidence) or not 0 <= confidence <= 1:
        raise ValueError(
            "LLM summary-quality response confidence must be a number from 0 to 1"
        )
    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale:
        raise ValueError(
            "LLM summary-quality response rationale must be a non-empty string"
        )
    evidence = _string_list(parsed.get("evidence"), "evidence")
    issues = _string_list(parsed.get("issues"), "issues")
    return {
        **{
            dimension: float(parsed[dimension])
            for dimension in SUMMARY_QUALITY_DIMENSIONS
        },
        "confidence": float(confidence),
        "rationale": rationale,
        "evidence": evidence,
        "issues": issues,
    }


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(
            f"LLM summary-quality response {field} must be an array of strings"
        )
    return value


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
