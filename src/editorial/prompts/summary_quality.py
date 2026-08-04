from __future__ import annotations

from editorial.llm import LLMMessage, Prompt
from editorial.models import Article


SUMMARY_QUALITY_PROMPT_VERSION = "summary-quality-v1"


def build_summary_quality_prompt(article: Article, summary: str) -> Prompt:
    body = article.content or article.summary or ""
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are an experienced editor assessing whether a generated "
                    "newsletter summary accurately represents its source article."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Article title:\n{article.title}\n\n"
                    f"Source article:\n{body}\n\n"
                    f"Generated summary:\n{summary}\n\n"
                    "Assess the generated summary only against the supplied source. "
                    "Return only JSON with fields: faithfulness, coverage, clarity, "
                    "and concision (each a number from 0 to 100); confidence (a "
                    "number from 0 to 1); rationale (a short string); evidence "
                    "(an array of short strings grounded in the source); and issues "
                    "(an array of short strings, empty when none are found)."
                ),
            ),
        ],
        metadata={"prompt_version": SUMMARY_QUALITY_PROMPT_VERSION},
    )
