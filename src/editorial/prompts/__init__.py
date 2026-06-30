from editorial.prompts.relevance import (
    RELEVANCE_PROMPT_VERSION,
    build_relevance_prompt,
)
from editorial.prompts.review import REVIEW_PROMPT_VERSION, build_review_prompt

__all__ = [
    "RELEVANCE_PROMPT_VERSION",
    "REVIEW_PROMPT_VERSION",
    "build_relevance_prompt",
    "build_review_prompt",
]
