import sys
from types import SimpleNamespace

import pytest

from editorial.config.models import ProcessorConfig
from editorial.extractors import LLMSummaryExtractor, build_extractor
from editorial.llm import OllamaProvider, OpenAIProvider
from editorial.llm import FakeLLMProvider
from editorial.models import Article
from editorial.prompts import SUMMARY_PROMPT_VERSION, build_summary_prompt


class RecordingResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="OpenAI summary", model=kwargs["model"])


class RecordingOpenAI:
    calls = []
    responses = None

    def __init__(self, **kwargs):
        self.__class__.calls.append(kwargs)
        self.__class__.responses = RecordingResponses()
        self.responses = self.__class__.responses


def test_summary_prompt_contains_title_and_body():
    article = Article(
        title="Industrial production rises",
        content="Output increased across several manufacturing categories.",
    )

    prompt = build_summary_prompt(article)

    assert prompt.messages[0].role == "system"
    assert (
        prompt.messages[0].content
        == "You are an experienced editor writing concise factual newsletter summaries."
    )
    assert prompt.messages[1].role == "user"
    assert "Industrial production rises" in prompt.messages[1].content
    assert "Output increased across several manufacturing categories." in (
        prompt.messages[1].content
    )
    assert "one paragraph" in prompt.messages[1].content
    assert "objective tone" in prompt.messages[1].content
    assert "Do not speculate" in prompt.messages[1].content
    assert "Do not use markdown" in prompt.messages[1].content
    assert "60-120 words" in prompt.messages[1].content
    assert prompt.metadata == {"prompt_version": SUMMARY_PROMPT_VERSION}


def test_llm_summary_extractor_calls_provider_once_and_stores_summary():
    article = Article(
        title="Industrial production rises",
        content="Output increased across several manufacturing categories.",
    )
    provider = FakeLLMProvider(
        response_text="Industrial output rose across several categories.",
        model="fake-summary-model",
    )
    extractor = LLMSummaryExtractor(provider)

    extraction = extractor.extract(article)

    assert provider.prompts == [build_summary_prompt(article)]
    assert extraction.article_id == article.id
    assert extraction.extractor == "llm_summary"
    assert extraction.extractor_version == "0.1.0"
    assert extraction.kind == "summary"
    assert extraction.payload["summary"] == (
        "Industrial output rose across several categories."
    )


def test_llm_summary_extractor_populates_ai_provenance_metadata():
    article = Article(title="Title", content="Body")
    provider = FakeLLMProvider(response_text="Summary", model="fake-summary-model")
    extractor = LLMSummaryExtractor(provider)

    extraction = extractor.extract(article)

    assert extraction.payload["metadata"] == {
        "generated_by": "llm",
        "provider": "fake",
        "model": "fake-summary-model",
        "prompt_version": SUMMARY_PROMPT_VERSION,
    }


def test_llm_summary_extractor_is_deterministic_with_fake_provider():
    article = Article(title="Title", content="Body")
    extractor = LLMSummaryExtractor(FakeLLMProvider(response_text="Same summary"))

    first = extractor.extract(article)
    second = extractor.extract(article)

    assert first.payload == second.payload


def test_build_llm_summary_extractor_from_config_uses_fake_provider():
    config = ProcessorConfig(
        type="llm_summary",
        settings={"response_text": "Configured summary", "model": "fake-config-model"},
    )

    extractor = build_extractor(config)
    extraction = extractor.extract(Article(title="Title", content="Body"))

    assert isinstance(extractor, LLMSummaryExtractor)
    assert extraction.payload["summary"] == "Configured summary"
    assert extraction.payload["metadata"]["model"] == "fake-config-model"


def test_build_llm_summary_extractor_from_provider_config_uses_fake_provider():
    config = ProcessorConfig(
        type="llm_summary",
        settings={
            "provider": {
                "type": "fake",
                "response_text": "Configured validation summary.",
                "model": "fake-summary-model",
            }
        },
    )

    extractor = build_extractor(config)
    extraction = extractor.extract(Article(title="Title", content="Body"))

    assert isinstance(extractor, LLMSummaryExtractor)
    assert extraction.payload == {
        "summary": "Configured validation summary.",
        "metadata": {
            "generated_by": "llm",
            "provider": "fake",
            "model": "fake-summary-model",
            "prompt_version": SUMMARY_PROMPT_VERSION,
        },
    }


def test_build_llm_summary_extractor_from_provider_config_builds_openai_provider(
    monkeypatch,
):
    RecordingOpenAI.calls = []
    monkeypatch.setenv("EDITORIAL_OPENAI_KEY", "secret-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=RecordingOpenAI))
    config = ProcessorConfig(
        type="llm_summary",
        settings={
            "provider": {
                "type": "openai",
                "model": "gpt-test",
                "api_key_env": "EDITORIAL_OPENAI_KEY",
                "base_url": "https://example.test/v1",
                "temperature": 0.2,
                "max_tokens": 90,
            }
        },
    )

    extractor = build_extractor(config)
    extraction = extractor.extract(Article(title="Title", content="Body"))

    assert isinstance(extractor, LLMSummaryExtractor)
    assert isinstance(extractor.provider, OpenAIProvider)
    assert RecordingOpenAI.calls == [
        {"api_key": "secret-key", "base_url": "https://example.test/v1"}
    ]
    assert RecordingOpenAI.responses is not None
    assert RecordingOpenAI.responses.calls[0]["model"] == "gpt-test"
    assert RecordingOpenAI.responses.calls[0]["temperature"] == 0.2
    assert RecordingOpenAI.responses.calls[0]["max_output_tokens"] == 90
    assert extraction.payload == {
        "summary": "OpenAI summary",
        "metadata": {
            "generated_by": "llm",
            "provider": "openai",
            "model": "gpt-test",
            "prompt_version": SUMMARY_PROMPT_VERSION,
        },
    }


def test_build_llm_summary_extractor_requires_openai_api_key(monkeypatch):
    monkeypatch.delenv("EDITORIAL_OPENAI_KEY", raising=False)
    config = ProcessorConfig(
        type="llm_summary",
        settings={
            "provider": {
                "type": "openai",
                "model": "gpt-test",
                "api_key_env": "EDITORIAL_OPENAI_KEY",
            }
        },
    )

    with pytest.raises(ValueError, match="EDITORIAL_OPENAI_KEY"):
        build_extractor(config)


def test_build_llm_summary_extractor_from_provider_config_builds_ollama_provider():
    config = ProcessorConfig(
        type="llm_summary",
        settings={
            "provider": {
                "type": "ollama",
                "model": "llama3.2",
                "base_url": "http://ollama.test:11434",
                "temperature": 0,
                "max_tokens": 180,
            }
        },
    )

    extractor = build_extractor(config)

    assert isinstance(extractor, LLMSummaryExtractor)
    assert isinstance(extractor.provider, OllamaProvider)
    assert extractor.provider.config.model == "llama3.2"
    assert extractor.provider.config.base_url == "http://ollama.test:11434"
    assert extractor.provider.config.temperature == 0
    assert extractor.provider.config.max_tokens == 180
