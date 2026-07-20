from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from editorial.llm.prompts import Prompt
from editorial.llm.response import LLMResponse


class OpenAIProviderConfig(BaseModel):
    model: str = Field(min_length=1)
    api_key: str | None = None
    base_url: str | None = None
    organization: str | None = None
    project: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        config: OpenAIProviderConfig,
        client: Any | None = None,
    ):
        self.config = config
        self.model = config.model
        self.client = client or self._build_client(config)

    def generate(self, prompt: Prompt) -> LLMResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
        }
        if self.config.temperature is not None:
            request["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            request["max_output_tokens"] = self.config.max_tokens
        response = self.client.responses.create(**request)
        metadata = dict(self.config.metadata)
        response_id = getattr(response, "id", None)
        if response_id is not None:
            metadata["response_id"] = response_id
        return LLMResponse(
            content=_response_content(response),
            model=getattr(response, "model", self.model),
            usage=_as_dict(getattr(response, "usage", None)),
            metadata=metadata,
        )

    def _build_client(self, config: OpenAIProviderConfig) -> Any:
        if config.api_key is None:
            raise ValueError("OpenAIProvider requires an explicit api_key or client")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAIProvider requires the optional openai dependency. "
                'Install with: pip install -e ".[openai]"'
            ) from exc

        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url is not None:
            kwargs["base_url"] = config.base_url
        if config.organization is not None:
            kwargs["organization"] = config.organization
        if config.project is not None:
            kwargs["project"] = config.project
        return OpenAI(**kwargs)


def _response_content(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        return str(output_text)
    output = getattr(response, "output", None)
    if output is not None:
        chunks: list[str] = []
        for item in output:
            for content in getattr(item, "content", []):
                text = getattr(content, "text", None)
                if text is not None:
                    chunks.append(str(text))
        return "".join(chunks)
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return dict(vars(value))
