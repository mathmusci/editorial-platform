from editorial.prompts.optimisation_request import (
    OPTIMISATION_REQUEST_PROMPT_VERSION,
    build_optimisation_request_prompt,
)
from editorial.prompts.relevance import (
    RELEVANCE_PROMPT_VERSION,
    build_relevance_prompt,
)
from editorial.prompts.review import REVIEW_PROMPT_VERSION, build_review_prompt
from editorial.prompts.summary import SUMMARY_PROMPT_VERSION, build_summary_prompt

__all__ = [
    "OPTIMISATION_REQUEST_PROMPT_VERSION",
    "RELEVANCE_PROMPT_VERSION",
    "REVIEW_PROMPT_VERSION",
    "SUMMARY_PROMPT_VERSION",
    "build_optimisation_request_prompt",
    "build_relevance_prompt",
    "build_review_prompt",
    "build_summary_prompt",
]