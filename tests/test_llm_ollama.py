import json
from urllib.error import URLError

import pytest

from editorial.llm import (
    LLMMessage,
    LLMProviderFactoryConfig,
    OllamaProvider,
    OllamaProviderConfig,
    Prompt,
    build_llm_provider,
)


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RecordingHTTPPost:
    def __init__(self, payload=None, exception=None):
        self.payload = payload or {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "Ollama answer"},
        }
        self.exception = exception
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if self.exception is not None:
            raise self.exception
        return FakeHTTPResponse(self.payload)


def _request_json(request):
    return json.loads(request.data.decode("utf-8"))


def test_llm_provider_factory_builds_ollama_provider():
    provider = build_llm_provider(
        LLMProviderFactoryConfig(provider="ollama", model="llama3.2")
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.config.model == "llama3.2"


def test_ollama_provider_uses_default_base_url():
    provider = build_llm_provider(
        LLMProviderFactoryConfig(provider="ollama", model="llama3.2")
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.config.base_url == "http://localhost:11434"


def test_ollama_provider_uses_custom_base_url():
    provider = build_llm_provider(
        LLMProviderFactoryConfig(
            provider="ollama",
            model="llama3.2",
            base_url="http://ollama.test:11434",
        )
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.config.base_url == "http://ollama.test:11434"


def test_ollama_provider_generates_request_and_maps_prompt_messages():
    http_post = RecordingHTTPPost()
    provider = OllamaProvider(
        OllamaProviderConfig(model="llama3.2", base_url="http://ollama.test"),
        http_post=http_post,
    )
    prompt = Prompt(
        messages=[
            LLMMessage(role="system", content="Be concise."),
            LLMMessage(role="user", content="Summarise this."),
            LLMMessage(role="assistant", content="Draft answer."),
        ]
    )

    provider.generate(prompt)

    request = http_post.calls[0]
    assert request.full_url == "http://ollama.test/api/chat"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert _request_json(request) == {
        "model": "llama3.2",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Summarise this."},
            {"role": "assistant", "content": "Draft answer."},
        ],
        "stream": False,
    }


def test_ollama_provider_parses_response():
    http_post = RecordingHTTPPost(
        {
            "model": "qwen3:8b",
            "message": {"role": "assistant", "content": "Parsed answer"},
        }
    )
    provider = OllamaProvider(
        OllamaProviderConfig(
            model="llama3.2",
            metadata={"purpose": "unit-test"},
        ),
        http_post=http_post,
    )

    response = provider.generate(
        Prompt(messages=[LLMMessage(role="user", content="Hello")])
    )

    assert response.content == "Parsed answer"
    assert response.model == "qwen3:8b"
    assert response.usage == {}
    assert response.metadata == {"purpose": "unit-test"}


def test_ollama_provider_maps_temperature_to_options():
    http_post = RecordingHTTPPost()
    provider = OllamaProvider(
        OllamaProviderConfig(model="llama3.2", temperature=0),
        http_post=http_post,
    )

    provider.generate(Prompt(messages=[LLMMessage(role="user", content="Hello")]))

    assert _request_json(http_post.calls[0])["options"] == {"temperature": 0}


def test_ollama_provider_maps_max_tokens_to_num_predict():
    http_post = RecordingHTTPPost()
    provider = OllamaProvider(
        OllamaProviderConfig(model="llama3.2", max_tokens=200),
        http_post=http_post,
    )

    provider.generate(Prompt(messages=[LLMMessage(role="user", content="Hello")]))

    assert _request_json(http_post.calls[0])["options"] == {"num_predict": 200}


def test_ollama_provider_maps_all_generation_options():
    http_post = RecordingHTTPPost()
    provider = OllamaProvider(
        OllamaProviderConfig(model="llama3.2", temperature=0, max_tokens=180),
        http_post=http_post,
    )

    provider.generate(Prompt(messages=[LLMMessage(role="user", content="Hello")]))

    assert _request_json(http_post.calls[0])["options"] == {
        "temperature": 0,
        "num_predict": 180,
    }


def test_ollama_provider_reports_connection_failure():
    http_post = RecordingHTTPPost(exception=URLError("connection refused"))
    provider = OllamaProvider(
        OllamaProviderConfig(
            model="llama3.2",
            base_url="http://ollama.test:11434",
        ),
        http_post=http_post,
    )

    with pytest.raises(RuntimeError, match="Ollama connection failed"):
        provider.generate(Prompt(messages=[LLMMessage(role="user", content="Hello")]))


def test_ollama_provider_requires_explicit_model():
    with pytest.raises(ValueError, match="requires an explicit model"):
        build_llm_provider(LLMProviderFactoryConfig(provider="ollama"))
