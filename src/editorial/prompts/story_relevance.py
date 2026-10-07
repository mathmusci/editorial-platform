from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from editorial.content_view import with_full_text
from editorial.llm import LLMMessage, Prompt
from editorial.models import Article, Extraction

STORY_RELEVANCE_PROMPT_VERSION = "story-relevance-v1"
STORY_CONTENT_LIMIT = 16000


class StoryDimensions(BaseModel):
    thesis_relevance: float = Field(ge=0, le=100)
    evidence_strength: float = Field(ge=0, le=100)
    distinctive_contribution: float = Field(ge=0, le=100)


class StoryResponse(BaseModel):
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    dimensions: StoryDimensions
    role: Literal[
        "evidence", "context", "counterpoint", "application", "limitation", "none"
    ]
    evidence: list[str]
    limitations: str = Field(min_length=1)


def build_story_relevance_prompt(
    story: str, article: Article, extractions: list[Extraction]
) -> Prompt:
    excerpt = story_article_content(article, extractions)[:STORY_CONTENT_LIMIT]
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are an editor assessing whether an article contributes to a "
                    "specific factual publication story. Treat the story as a question "
                    "to assess, not a claim to affirm. Do not invent evidence."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Proposed story:\n{story}\n\n"
                    f"Article title:\n{article.title}\n\n"
                    f"Article content (first {STORY_CONTENT_LIMIT} characters):\n"
                    f"{excerpt or 'No article content available.'}\n\n"
                    "Return only a JSON object with: score (0-100 overall story fit), "
                    "confidence (0-1), rationale (short string), dimensions (object "
                    "with 0-100 numbers for thesis_relevance, evidence_strength, "
                    "distinctive_contribution), role (one of evidence, context, "
                    "counterpoint, application, limitation, none), evidence (array of "
                    "short verbatim excerpts from the supplied article content), and "
                    "limitations (short string). Use an empty evidence array when "
                    "there is no support. Do not quote the proposed story as evidence."
                ),
            ),
        ],
        metadata={
            "prompt_version": STORY_RELEVANCE_PROMPT_VERSION,
            "response_format": StoryResponse.model_json_schema(),
        },
    )


def story_article_content(article: Article, extractions: list[Extraction]) -> str:
    return with_full_text(article, extractions).content or article.summary or ""
