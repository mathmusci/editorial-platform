import sys
from types import SimpleNamespace

import pytest

from editorial.llm import (
    LLMMessage,
    LLMProviderFactoryConfig,
    OpenAIProvider,
    OpenAIProviderConfig,
    Prompt,
    build_llm_provider,
)
from editorial.llm.openai import _response_content
from editorial.llm.testing import FakeLLMProvider


class RecordingResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class RecordingClient:
    def __init__(self, response):
        self.responses = RecordingResponses(response)


class RecordingOpenAI:
    calls = []

    def __init__(self, **kwargs):
        self.__class__.calls.append(kwargs)
        self.responses = RecordingResponses(
            SimpleNamespace(output_text="unused", model=kwargs.get("model"))
        )


def test_openai_provider_generates_with_injected_client():
    response = SimpleNamespace(
        id="resp_123",
        output_text="OpenAI answer",
        model="test-model",
        usage={"input_tokens": 3, "output_tokens": 2},
    )
    client = RecordingClient(response)
    provider = OpenAIProvider(
        OpenAIProviderConfig(
            model="test-model",
            api_key=None,
            metadata={"purpose": "unit-test"},
        ),
        client=client,
    )
    prompt = Prompt(
        messages=[
            LLMMessage(role="system", content="Be concise."),
            LLMMessage(role="user", content="Hello"),
        ]
    )

    llm_response = provider.generate(prompt)

    assert client.responses.calls == [
        {
            "model": "test-model",
            "input": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Hello"},
            ],
        }
    ]
    assert llm_response.content == "OpenAI answer"
    assert llm_response.model == "test-model"
    assert llm_response.usage == {"input_tokens": 3, "output_tokens": 2}
    assert llm_response.metadata == {
        "purpose": "unit-test",
        "response_id": "resp_123",
    }


def test_openai_provider_requires_explicit_api_key_without_client():
    with pytest.raises(ValueError, match="explicit api_key or client"):
        OpenAIProvider(OpenAIProviderConfig(model="test-model"))


def test_openai_provider_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    provider = OpenAIProvider.__new__(OpenAIProvider)

    with pytest.raises(RuntimeError, match="optional openai dependency"):
        provider._build_client(OpenAIProviderConfig(model="test-model", api_key="key"))


def test_response_content_falls_back_to_output_items():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(text="First "),
                    SimpleNamespace(text="second"),
                ]
            )
        ]
    )

    assert _response_content(response) == "First second"


def test_llm_provider_factory_builds_fake_provider():
    provider = build_llm_provider(
        LLMProviderFactoryConfig(
            provider="fake",
            response_text="Factory fake",
            metadata={"source": "factory"},
        )
    )

    assert isinstance(provider, FakeLLMProvider)
    assert provider.generate(
        Prompt(messages=[LLMMessage(role="user", content="Hello")])
    ).metadata == {"source": "factory"}


def test_llm_provider_factory_requires_openai_model():
    with pytest.raises(ValueError, match="requires an explicit model"):
        build_llm_provider(LLMProviderFactoryConfig(provider="openai"))


def test_llm_provider_factory_reads_openai_key_from_default_env(monkeypatch):
    RecordingOpenAI.calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=RecordingOpenAI))

    provider = build_llm_provider(
        LLMProviderFactoryConfig(
            provider="openai",
            model="test-model",
            metadata={"purpose": "factory-test"},
        )
    )

    assert isinstance(provider, OpenAIProvider)
    assert RecordingOpenAI.calls == [{"api_key": "secret-key"}]
    assert provider.config.model == "test-model"
    assert provider.config.metadata == {"purpose": "factory-test"}
    assert "api_key" not in provider.config.metadata


def test_llm_provider_factory_reads_openai_key_from_custom_env(monkeypatch):
    RecordingOpenAI.calls = []
    monkeypatch.setenv("EDITORIAL_OPENAI_KEY", "custom-secret")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=RecordingOpenAI))

    build_llm_provider(
        LLMProviderFactoryConfig(
            provider="openai",
            model="test-model",
            api_key_env="EDITORIAL_OPENAI_KEY",
            base_url="https://example.test/v1",
            organization="org_123",
            project="proj_123",
        )
    )

    assert RecordingOpenAI.calls == [
        {
            "api_key": "custom-secret",
            "base_url": "https://example.test/v1",
            "organization": "org_123",
            "project": "proj_123",
        }
    ]


def test_llm_provider_factory_does_not_store_resolved_key(monkeypatch):
    RecordingOpenAI.calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=RecordingOpenAI))

    config = LLMProviderFactoryConfig(provider="openai", model="test-model")
    provider = build_llm_provider(config)

    assert config.model_dump() == {
        "provider": "openai",
        "response_text": "Fake response",
        "model": "test-model",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "organization": None,
        "project": None,
        "metadata": {},
    }
    assert provider.config.api_key == "secret-key"
    assert "secret-key" not in str(config.model_dump())
    assert "secret-key" not in str(provider.config.metadata)


def test_llm_provider_factory_requires_configured_env_var(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_llm_provider(
            LLMProviderFactoryConfig(provider="openai", model="test-model")
        )
