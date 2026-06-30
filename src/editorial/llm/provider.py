from __future__ import annotations

from typing import Protocol

from editorial.llm.prompts import Prompt
from editorial.llm.response import LLMResponse


class LLMProvider(Protocol):
    name: str

    def generate(self, prompt: Prompt) -> LLMResponse: ...
