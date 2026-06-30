import pytest

from editorial.config.models import ProcessorConfig
from editorial.evaluators import LLMRelevanceEvaluator, build_evaluator
from editorial.llm import FakeLLMProvider
from editorial.models import Article, Extraction
from editorial.prompts import RELEVANCE_PROMPT_VERSION, build_relevance_prompt


def _article() -> Article:
    return Article(
        title="Industrial statistics show output growth",
        summary="Manufacturing output rose in the latest data.",
        content="The article reports updated industrial production statistics.",
    )


def _summary_extraction(article: Article) -> Extraction:
    return Extraction(
        article_id=article.id,
        extractor="llm_summary",
        kind="summary",
        payload={"summary": "Industrial output rose in the latest statistics."},
    )


def test_relevance_prompt_contains_article_and_extraction_summary():
    article = _article()
    extraction = _summary_extraction(article)

    prompt = build_relevance_prompt(article, [extraction])

    assert prompt.messages[0].role == "system"
    assert "assessing article relevance" in prompt.messages[0].content
    assert prompt.messages[1].role == "user"
    assert article.title in prompt.messages[1].content
    assert article.content in prompt.messages[1].content
    assert "Industrial output rose in the latest statistics." in (
        prompt.messages[1].content
    )
    assert "score" in prompt.messages[1].content
    assert "confidence" in prompt.messages[1].content
    assert "rationale" in prompt.messages[1].content
    assert prompt.metadata == {"prompt_version": RELEVANCE_PROMPT_VERSION}


def test_llm_relevance_evaluator_calls_provider_once_and_creates_evaluation():
    article = _article()
    extraction = _summary_extraction(article)
    provider = FakeLLMProvider(
        response_text=(
            '{"score": 75, "confidence": 0.8, '
            '"rationale": "Relevant to industrial statistics."}'
        ),
        model="fake-relevance-model",
    )
    evaluator = LLMRelevanceEvaluator(provider)

    evaluation = evaluator.evaluate(article, [extraction])

    assert provider.prompts == [build_relevance_prompt(article, [extraction])]
    assert evaluation.article_id == article.id
    assert evaluation.evaluator == "llm_relevance"
    assert evaluation.evaluator_version == "0.1.0"
    assert evaluation.kind == "relevance"
    assert evaluation.criterion == "editorial_relevance"
    assert evaluation.score == 75
    assert evaluation.confidence == 0.8
    assert evaluation.rationale == "Relevant to industrial statistics."
    assert evaluation.payload["raw_response"] == provider.response_text


def test_llm_relevance_evaluator_populates_ai_provenance_metadata():
    article = _article()
    provider = FakeLLMProvider(
        response_text='{"score": 40, "confidence": 0.5, "rationale": "Partial fit."}',
        model="fake-relevance-model",
    )
    evaluator = LLMRelevanceEvaluator(provider, criterion="custom_relevance")

    evaluation = evaluator.evaluate(article, [])

    assert evaluation.criterion == "custom_relevance"
    assert evaluation.payload["metadata"] == {
        "generated_by": "llm",
        "provider": "fake",
        "model": "fake-relevance-model",
        "prompt_version": RELEVANCE_PROMPT_VERSION,
    }


def test_llm_relevance_evaluator_rejects_invalid_json():
    evaluator = LLMRelevanceEvaluator(FakeLLMProvider(response_text="not json"))

    with pytest.raises(ValueError, match="valid JSON"):
        evaluator.evaluate(_article(), [])


@pytest.mark.parametrize(
    "response",
    [
        '{"confidence": 0.8, "rationale": "Missing score."}',
        '{"score": -1, "confidence": 0.8, "rationale": "Bad score."}',
        '{"score": 101, "confidence": 0.8, "rationale": "Bad score."}',
        '{"score": "75", "confidence": 0.8, "rationale": "Bad score."}',
        '{"score": 75, "rationale": "Missing confidence."}',
        '{"score": 75, "confidence": -0.1, "rationale": "Bad confidence."}',
        '{"score": 75, "confidence": 1.1, "rationale": "Bad confidence."}',
        '{"score": 75, "confidence": "0.8", "rationale": "Bad confidence."}',
        '{"score": 75, "confidence": 0.8, "rationale": ""}',
    ],
)
def test_llm_relevance_evaluator_rejects_invalid_score_confidence_or_rationale(
    response,
):
    evaluator = LLMRelevanceEvaluator(FakeLLMProvider(response_text=response))

    with pytest.raises(ValueError):
        evaluator.evaluate(_article(), [])


def test_build_llm_relevance_evaluator_from_config_uses_fake_provider():
    config = ProcessorConfig(
        type="llm_relevance",
        settings={
            "provider": "fake",
            "response_text": (
                '{"score": 75, "confidence": 0.8, '
                '"rationale": "Relevant to industrial statistics."}'
            ),
            "model": "fake-relevance-model",
            "criterion": "newsletter_relevance",
        },
    )

    evaluator = build_evaluator(config)
    evaluation = evaluator.evaluate(_article(), [])

    assert isinstance(evaluator, LLMRelevanceEvaluator)
    assert evaluation.score == 75
    assert evaluation.confidence == 0.8
    assert evaluation.criterion == "newsletter_relevance"
    assert evaluation.payload["metadata"]["model"] == "fake-relevance-model"
