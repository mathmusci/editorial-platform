import pytest

from editorial.config.models import ProcessorConfig
from editorial.evaluators import LLMStoryRelevanceEvaluator, build_evaluator
from editorial.evaluators.factory import describe_evaluator
from editorial.llm import FakeLLMProvider
from editorial.models import Article, Extraction


def _response(evidence='["Forecasts are uncertain."]'):
    return (
        '{"score": 78, "confidence": 0.7, "rationale": "Direct fit.", '
        '"dimensions": {"thesis_relevance": 80, "evidence_strength": 75, '
        '"distinctive_contribution": 60}, "role": "evidence", '
        f'"evidence": {evidence}, "limitations": "One small study."}}'
    )


def test_story_evaluator_uses_full_text_and_stores_inspectable_evidence():
    article = Article(title="Forecasting paper", summary="Short abstract")
    extraction = Extraction(
        article_id=article.id,
        extractor="arxiv_full_text",
        kind="full_text",
        payload={"content": "Forecasts are uncertain. Methods are compared."},
    )
    provider = FakeLLMProvider(response_text=_response(), model="local-model")
    evaluator = LLMStoryRelevanceEvaluator(provider, "Uncertainty in forecasting")

    result = evaluator.evaluate(article, [extraction])

    assert "Uncertainty in forecasting" in provider.prompts[0].messages[1].content
    assert "Forecasts are uncertain." in provider.prompts[0].messages[1].content
    schema = provider.prompts[0].metadata["response_format"]
    assert set(schema["properties"]["role"]["enum"]) == {
        "evidence",
        "context",
        "counterpoint",
        "application",
        "limitation",
        "none",
    }
    assert result.kind == "story_relevance"
    assert result.criterion == "Uncertainty in forecasting"
    assert result.score == 78
    assert result.payload["dimensions"]["evidence_strength"] == 75
    assert result.payload["role"] == "evidence"
    assert result.payload["evidence"] == ["Forecasts are uncertain."]
    assert result.payload["metadata"]["provider"] == "fake"
    assert result.payload["metadata"]["model"] == "local-model"


def test_factory_builds_story_evaluator():
    config = ProcessorConfig(
        type="llm_story_relevance",
        settings={
            "story": "Uncertainty in forecasting",
            "provider": {"type": "fake", "response_text": _response("[]")},
        },
    )
    evaluator = build_evaluator(config)
    result = evaluator.evaluate(Article(title="Forecasting", content="No quote."), [])

    assert isinstance(evaluator, LLMStoryRelevanceEvaluator)
    assert describe_evaluator(config).kind == "story_relevance"
    assert result.payload["evidence"] == []


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        _response('["Invented quotation."]'),
        _response().replace('"score": 78', '"score": 101'),
        _response().replace('"role": "evidence"', '"role": "invented"'),
        _response().replace('"evidence_strength": 75', '"evidence_strength": null'),
    ],
)
def test_story_evaluator_rejects_invalid_or_unsupported_response(response):
    evaluator = LLMStoryRelevanceEvaluator(FakeLLMProvider(response), "A story")

    with pytest.raises(ValueError):
        evaluator.evaluate(
            Article(title="Paper", content="Forecasts are uncertain."), []
        )


def test_story_evaluator_requires_story():
    with pytest.raises(ValueError, match="non-empty story"):
        LLMStoryRelevanceEvaluator(FakeLLMProvider("{}"), " ")
