from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from editorial.llm.openai import OpenAIProvider, OpenAIProviderConfig
from editorial.llm.provider import LLMProvider
from editorial.llm.testing import FakeLLMProvider


class LLMProviderFactoryConfig(BaseModel):
    provider: Literal["fake", "openai"]
    response_text: str = "Fake response"
    model: str | None = None
    api_key: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


def build_llm_provider(config: LLMProviderFactoryConfig) -> LLMProvider:
    if config.provider == "fake":
        return FakeLLMProvider(
            response_text=config.response_text,
            model=config.model or "fake-llm",
            metadata=config.metadata,
        )
    if config.model is None:
        raise ValueError("OpenAI LLM provider requires an explicit model")
    return OpenAIProvider(
        OpenAIProviderConfig(
            model=config.model,
            api_key=config.api_key,
            metadata=config.metadata,
        )
    )
