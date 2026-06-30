import pytest
from pydantic import ValidationError

from editorial.llm import (
    FakeLLMProvider,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    Prompt,
)


def test_llm_message_role_validation():
    message = LLMMessage(role="user", content="Summarise this.")

    assert message.role == "user"
    assert message.content == "Summarise this."

    with pytest.raises(ValidationError):
        LLMMessage(role="tool", content="Unsupported role")


def test_prompt_requires_messages_and_preserves_metadata():
    message = LLMMessage(role="system", content="You are careful.")
    prompt = Prompt(messages=[message], metadata={"purpose": "test"})

    assert prompt.messages == [message]
    assert prompt.metadata == {"purpose": "test"}

    with pytest.raises(ValidationError):
        Prompt(messages=[])


def test_llm_response_defaults_are_independent():
    first = LLMResponse(content="First")
    second = LLMResponse(content="Second")

    first.usage["tokens"] = 3
    first.metadata["trace"] = "a"

    assert first.model is None
    assert second.usage == {}
    assert second.metadata == {}


def test_fake_llm_provider_returns_configured_response():
    provider = FakeLLMProvider(
        response_text="Deterministic answer",
        model="fake-test-model",
        usage={"input_tokens": 4, "output_tokens": 2},
        metadata={"provider": "test"},
    )
    prompt = Prompt(messages=[LLMMessage(role="user", content="Hello")])

    response = provider.generate(prompt)

    assert response == LLMResponse(
        content="Deterministic answer",
        model="fake-test-model",
        usage={"input_tokens": 4, "output_tokens": 2},
        metadata={"provider": "test"},
    )


def test_fake_llm_provider_records_prompts():
    provider = FakeLLMProvider(response_text="OK")
    first = Prompt(messages=[LLMMessage(role="user", content="First")])
    second = Prompt(messages=[LLMMessage(role="assistant", content="Second")])

    provider.generate(first)
    provider.generate(second)

    assert provider.prompts == [first, second]


def test_public_llm_imports_and_protocol_shape():
    provider: LLMProvider = FakeLLMProvider(response_text="OK")
    prompt = Prompt(messages=[LLMMessage(role="user", content="Hello")])

    assert provider.name == "fake"
    assert provider.generate(prompt).content == "OK"
