from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    content: str
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
