from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)
