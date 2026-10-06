from __future__ import annotations

import json
import math

from editorial.llm import LLMProvider
from editorial.models import Article, Evaluation, Extraction
from editorial.prompts.story_relevance import (
    STORY_CONTENT_LIMIT,
    STORY_RELEVANCE_PROMPT_VERSION,
    build_story_relevance_prompt,
    story_article_content,
)

DIMENSIONS = ("thesis_relevance", "evidence_strength", "distinctive_contribution")
ROLES = {"evidence", "context", "counterpoint", "application", "limitation", "none"}


class LLMStoryRelevanceEvaluator:
    name = "llm_story_relevance"
    version = "0.1.0"

    def __init__(self, provider: LLMProvider, story: str):
        if not isinstance(story, str) or not story.strip():
            raise ValueError("llm_story_relevance requires a non-empty story")
        self.provider = provider
        self.story = story.strip()

    def evaluate(self, article: Article, extractions: list[Extraction]) -> Evaluation:
        prompt = build_story_relevance_prompt(self.story, article, extractions)
        response = self.provider.generate(prompt)
        parsed = _parse_story_response(response.content)
        article_excerpt = story_article_content(article, extractions)[
            :STORY_CONTENT_LIMIT
        ]
        if any(quote not in article_excerpt for quote in parsed["evidence"]):
            raise ValueError("Story evidence must quote the supplied article content")
        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="story_relevance",
            criterion=self.story,
            score=parsed["score"],
            confidence=parsed["confidence"],
            rationale=parsed["rationale"],
            payload={
                "story": self.story,
                "dimensions": parsed["dimensions"],
                "role": parsed["role"],
                "evidence": parsed["evidence"],
                "limitations": parsed["limitations"],
                "content_characters_supplied": min(
                    len(story_article_content(article, extractions)),
                    STORY_CONTENT_LIMIT,
                ),
                "raw_response": response.content,
                "metadata": {
                    "generated_by": "llm",
                    "provider": self.provider.name,
                    "model": response.model,
                    "prompt_version": STORY_RELEVANCE_PROMPT_VERSION,
                },
            },
        )


def _parse_story_response(content: str) -> dict:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Story relevance response must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Story relevance response must be a JSON object")
    for key, maximum in (("score", 100), ("confidence", 1)):
        value = parsed.get(key)
        if not _number_in_range(value, maximum):
            raise ValueError(f"Story relevance {key} must be between 0 and {maximum}")
    dimensions = parsed.get("dimensions")
    if not isinstance(dimensions, dict) or any(
        not _number_in_range(dimensions.get(key), 100) for key in DIMENSIONS
    ):
        raise ValueError("Story relevance dimensions must contain three 0-100 scores")
    for key in ("rationale", "limitations"):
        if not isinstance(parsed.get(key), str) or not parsed[key].strip():
            raise ValueError(f"Story relevance {key} must be a non-empty string")
    if parsed.get("role") not in ROLES:
        raise ValueError(
            f"Story relevance role {str(parsed.get('role'))[:80]!r} is invalid; "
            f"expected one of {', '.join(sorted(ROLES))}"
        )
    evidence = parsed.get("evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise ValueError("Story relevance evidence must be an array of quotations")
    return parsed


def _number_in_range(value: object, maximum: float) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= maximum
    )
