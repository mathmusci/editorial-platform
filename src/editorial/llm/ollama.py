from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from editorial.llm.prompts import Prompt
from editorial.llm.response import LLMResponse


class OllamaProviderConfig(BaseModel):
    model: str = Field(min_length=1)
    base_url: str = "http://localhost:11434"
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        config: OllamaProviderConfig,
        http_post: Callable[[Request], Any] | None = None,
    ):
        self.config = config
        self.model = config.model
        self.http_post = http_post or urlopen

    def generate(self, prompt: Prompt) -> LLMResponse:
        request_payload = self._build_request_payload(prompt)
        request = Request(
            _chat_url(self.config.base_url),
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response_payload = self._post_json(request)
        message = response_payload.get("message", {})
        content = message.get("content", "")
        return LLMResponse(
            content=str(content),
            model=response_payload.get("model", self.model),
            usage={},
            metadata=dict(self.config.metadata),
        )

    def _build_request_payload(self, prompt: Prompt) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
            "stream": False,
        }
        options: dict[str, Any] = {}
        if self.config.temperature is not None:
            options["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            options["num_predict"] = self.config.max_tokens
        if options:
            request["options"] = options
        return request

    def _post_json(self, request: Request) -> dict[str, Any]:
        try:
            with self.http_post(request) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RuntimeError(
                "Ollama request failed "
                f"for base_url {self.config.base_url!r}: HTTP {exc.code}"
            ) from exc
        except (OSError, URLError) as exc:
            raise RuntimeError(
                f"Ollama connection failed for base_url {self.config.base_url!r}"
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Ollama returned an invalid JSON response "
                f"for base_url {self.config.base_url!r}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Ollama returned an unexpected response "
                f"for base_url {self.config.base_url!r}"
            )
        return payload


def _chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/chat"
