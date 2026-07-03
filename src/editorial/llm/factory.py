from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from editorial.llm.openai import OpenAIProvider, OpenAIProviderConfig
from editorial.llm.provider import LLMProvider
from editorial.llm.testing import FakeLLMProvider


class LLMProviderFactoryConfig(BaseModel):
    provider: Literal["fake", "openai"]
    response_text: str = "Fake response"
    model: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    organization: str | None = None
    project: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
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
    api_key = os.environ.get(config.api_key_env)
    if api_key is None:
        raise ValueError(
            f"OpenAI LLM provider requires API key env var {config.api_key_env!r}"
        )
    return OpenAIProvider(
        OpenAIProviderConfig(
            model=config.model,
            api_key=api_key,
            base_url=config.base_url,
            organization=config.organization,
            project=config.project,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            metadata=config.metadata,
        )
    )
