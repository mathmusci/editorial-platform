from __future__ import annotations

import json
from typing import Any

from editorial.llm import LLMProvider
from editorial.models import OptimisationRequest
from editorial.prompts import (
    OPTIMISATION_REQUEST_PROMPT_VERSION,
    build_optimisation_request_prompt,
)


class LLMOptimisationRequestBuilder:
    name = "llm_optimisation_request_builder"
    version = "0.1.0"

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def build(
        self,
        publication: str | None,
        editor_instruction: str,
        created_by: str | None = None,
    ) -> OptimisationRequest:
        prompt = build_optimisation_request_prompt(publication, editor_instruction)
        response = self.provider.generate(prompt)
        parsed = _parse_optimisation_request_response(response.content)
        metadata = {
            **parsed["metadata"],
            "generated_by": "llm",
            "provider": self.provider.name,
            "model": response.model,
            "prompt_version": OPTIMISATION_REQUEST_PROMPT_VERSION,
            "source_instruction": editor_instruction,
        }
        return OptimisationRequest(
            publication=publication,
            strategy=parsed["strategy"],
            settings=parsed["settings"],
            constraints=parsed["constraints"],
            goals=parsed["goals"],
            preferences=parsed["preferences"],
            created_by=created_by,
            metadata=metadata,
        )


def _parse_optimisation_request_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM optimisation request response must be valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM optimisation request response must be a JSON object")

    strategy = parsed.get("strategy")
    if not isinstance(strategy, str) or not strategy:
        raise ValueError(
            "LLM optimisation request response strategy must be a non-empty string"
        )

    for field in ["settings", "constraints", "goals", "preferences", "metadata"]:
        if not isinstance(parsed.get(field), dict):
            raise ValueError(
                f"LLM optimisation request response {field} must be an object"
            )

    return {
        "strategy": strategy,
        "settings": parsed["settings"],
        "constraints": parsed["constraints"],
        "goals": parsed["goals"],
        "preferences": parsed["preferences"],
        "metadata": parsed["metadata"],
    }
