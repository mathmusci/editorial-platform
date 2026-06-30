from __future__ import annotations

from editorial.llm import LLMMessage, Prompt
from editorial.models import Article


SUMMARY_PROMPT_VERSION = "summary-v1"


def build_summary_prompt(article: Article) -> Prompt:
    body = article.content or article.summary or ""
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are an experienced editor writing concise factual "
                    "newsletter summaries."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Article title:\n{article.title}\n\n"
                    f"Article body:\n{body}\n\n"
                    "Write one paragraph in an objective tone. Do not speculate. "
                    "Do not use markdown. Aim for approximately 60-120 words."
                ),
            ),
        ],
        metadata={"prompt_version": SUMMARY_PROMPT_VERSION},
    )
