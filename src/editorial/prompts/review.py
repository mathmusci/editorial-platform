from __future__ import annotations

from uuid import UUID

from editorial.llm import LLMMessage, Prompt


REVIEW_PROMPT_VERSION = "review-v1"


def build_review_prompt(
    artefact_type: str,
    artefact_id: UUID,
    artefact_context: str,
) -> Prompt:
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are an experienced editorial reviewer. Provide a "
                    "recommendation only; human editors make final decisions."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Artefact type:\n{artefact_type}\n\n"
                    f"Artefact id:\n{artefact_id}\n\n"
                    f"Artefact context:\n{artefact_context}\n\n"
                    "Return only JSON with fields: decision, comments, findings, "
                    "and recommendations. decision must be one of approve, reject, "
                    "needs_changes, or comment. findings and recommendations must "
                    "be objects."
                ),
            ),
        ],
        metadata={"prompt_version": REVIEW_PROMPT_VERSION},
    )
