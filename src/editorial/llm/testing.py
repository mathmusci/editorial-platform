from __future__ import annotations

from typing import Any

from editorial.llm.prompts import Prompt
from editorial.llm.response import LLMResponse


class FakeLLMProvider:
    name = "fake"

    def __init__(
        self,
        response_text: str = "Fake response",
        model: str | None = "fake-llm",
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.response_text = response_text
        self.model = model
        self.usage = usage or {}
        self.metadata = metadata or {}
        self.prompts: list[Prompt] = []

    def generate(self, prompt: Prompt) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(
            content=self.response_text,
            model=self.model,
            usage=dict(self.usage),
            metadata=dict(self.metadata),
        )
