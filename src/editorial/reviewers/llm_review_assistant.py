from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from editorial.llm import LLMProvider
from editorial.models import Review, ReviewDecision
from editorial.prompts import REVIEW_PROMPT_VERSION, build_review_prompt


class LLMReviewAssistant:
    name = "llm_review_assistant"
    version = "0.1.0"

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def recommend(
        self,
        artefact_type: str,
        artefact_id: UUID,
        artefact_context: str,
    ) -> Review:
        prompt = build_review_prompt(artefact_type, artefact_id, artefact_context)
        response = self.provider.generate(prompt)
        parsed = _parse_review_response(response.content)
        return Review(
            artefact_type=artefact_type,
            artefact_id=artefact_id,
            reviewer=self.name,
            decision=parsed["decision"],
            comments=parsed["comments"],
            findings=parsed["findings"],
            recommendations=parsed["recommendations"],
            metadata={
                "generated_by": "llm",
                "provider": self.provider.name,
                "model": response.model,
                "prompt_version": REVIEW_PROMPT_VERSION,
            },
        )


def _parse_review_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM review response must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM review response must be a JSON object")

    decision = parsed.get("decision")
    if decision not in {item.value for item in ReviewDecision}:
        raise ValueError(
            "LLM review response decision must be one of approve, reject, "
            "needs_changes, or comment"
        )
    comments = parsed.get("comments")
    if not isinstance(comments, str):
        raise ValueError("LLM review response comments must be a string")
    findings = parsed.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("LLM review response findings must be an object")
    recommendations = parsed.get("recommendations")
    if not isinstance(recommendations, dict):
        raise ValueError("LLM review response recommendations must be an object")

    return {
        "decision": ReviewDecision(decision),
        "comments": comments,
        "findings": findings,
        "recommendations": recommendations,
    }
