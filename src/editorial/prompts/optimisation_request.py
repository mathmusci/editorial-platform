from __future__ import annotations

from editorial.llm import LLMMessage, Prompt


OPTIMISATION_REQUEST_PROMPT_VERSION = "optimisation-request-v1"


def build_optimisation_request_prompt(
    publication: str | None,
    editor_instruction: str,
) -> Prompt:
    publication_text = publication or "Unspecified"
    return Prompt(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You help editors convert natural-language editorial intent "
                    "into structured optimisation request JSON."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Publication:\n{publication_text}\n\n"
                    f"Editor instruction:\n{editor_instruction}\n\n"
                    "Return only JSON with fields: strategy, settings, constraints, "
                    "goals, preferences, and metadata. strategy must be a non-empty "
                    "string. settings, constraints, goals, preferences, and metadata "
                    "must be objects."
                ),
            ),
        ],
        metadata={"prompt_version": OPTIMISATION_REQUEST_PROMPT_VERSION},
    )
