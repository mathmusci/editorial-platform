from __future__ import annotations

from editorial.llm import LLMMessage, Prompt
from editorial.models import Article, Extraction


RELEVANCE_PROMPT_VERSION = "relevance-v1"


def build_relevance_prompt(article: Article, extractions: list[Extraction]) -> Prompt:
    body = article.content or article.summary or ""
    extraction_text = _extraction_text(extractions)
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are an experienced editor assessing article relevance "
                    "for a factual newsletter."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Article title:\n{article.title}\n\n"
                    f"Article body:\n{body}\n\n"
                    f"Available extraction summaries:\n{extraction_text}\n\n"
                    "Assess editorial relevance for the newsletter. Return only JSON "
                    "with fields: score (number from 0 to 100), confidence (number "
                    "from 0 to 1), and rationale (short string)."
                ),
            ),
        ],
        metadata={"prompt_version": RELEVANCE_PROMPT_VERSION},
    )


def _extraction_text(extractions: list[Extraction]) -> str:
    lines: list[str] = []
    for extraction in extractions:
        summary = extraction.payload.get("summary")
        if isinstance(summary, str) and summary:
            lines.append(f"- {extraction.kind}: {summary}")
    return "\n".join(lines) if lines else "None."
