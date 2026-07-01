from editorial.config.models import ProcessorConfig
from editorial.extractors import LLMSummaryExtractor, build_extractor
from editorial.llm import FakeLLMProvider
from editorial.models import Article
from editorial.prompts import SUMMARY_PROMPT_VERSION, build_summary_prompt


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
