from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from editorial.llm.messages import LLMMessage


class Prompt(BaseModel):
    messages: list[LLMMessage] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
