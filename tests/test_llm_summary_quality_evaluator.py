import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.config.models import ProcessorConfig
from editorial.evaluators import LLMSummaryQualityEvaluator, build_evaluator
from editorial.llm import FakeLLMProvider, OllamaProvider, OpenAIProvider
from editorial.models import Article, Extraction
from editorial.prompts import (
    SUMMARY_QUALITY_PROMPT_VERSION,
    build_summary_quality_prompt,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


VALID_RESPONSE = (
    '{"faithfulness": 90, "coverage": 80, "clarity": 70, '
    '"concision": 60, "confidence": 0.85, '
    '"rationale": "Accurate and clear, with one omitted detail.", '
    '"evidence": ["Industrial output rose."], '
    '"issues": ["The regional breakdown is omitted."]}'
)


class RecordingResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=VALID_RESPONSE, model=kwargs["model"])


class RecordingOpenAI:
    calls = []
    responses = None

    def __init__(self, **kwargs):
        self.__class__.calls.append(kwargs)
        self.__class__.responses = RecordingResponses()
        self.responses = self.__class__.responses


def _article() -> Article:
    return Article(
        title="Industrial production rises",
        summary="Manufacturing output rose in the latest data.",
        content=(
            "Industrial output rose by 2 percent. Growth was broad, although the "
            "regional breakdown showed weaker production in the north."
        ),
    )


def _summary_extraction(
    article: Article,
    *,
    extractor: str = "llm_summary",
    summary: object = "Industrial output rose by 2 percent across the economy.",
) -> Extraction:
    return Extraction(
        article_id=article.id,
        extractor=extractor,
        kind="summary",
        payload={"summary": summary},
    )


def test_summary_quality_prompt_contains_source_summary_and_schema():
    article = _article()
    summary = "Industrial output rose by 2 percent."

    prompt = build_summary_quality_prompt(article, summary)

    assert prompt.messages[0].role == "system"
    assert "assessing whether a generated" in prompt.messages[0].content
    assert article.title in prompt.messages[1].content
    assert article.content in prompt.messages[1].content
    assert summary in prompt.messages[1].content
    for field in (
        "faithfulness",
        "coverage",
        "clarity",
        "concision",
        "confidence",
        "rationale",
        "evidence",
        "issues",
    ):
        assert field in prompt.messages[1].content
    assert prompt.metadata == {"prompt_version": SUMMARY_QUALITY_PROMPT_VERSION}


def test_summary_quality_evaluator_calls_provider_and_creates_evaluation():
    article = _article()
    extraction = _summary_extraction(article)
    provider = FakeLLMProvider(
        response_text=VALID_RESPONSE,
        model="fake-quality-model",
    )
    evaluator = LLMSummaryQualityEvaluator(provider)

    evaluation = evaluator.evaluate(article, [extraction])

    assert provider.prompts == [
        build_summary_quality_prompt(article, extraction.payload["summary"])
    ]
    assert evaluation.article_id == article.id
    assert evaluation.evaluator == "llm_summary_quality"
    assert evaluation.evaluator_version == "0.1.0"
    assert evaluation.kind == "summary_quality"
    assert evaluation.criterion == "summary_quality"
    assert evaluation.score == 75
    assert evaluation.confidence == 0.85
    assert evaluation.rationale == ("Accurate and clear, with one omitted detail.")
    assert evaluation.payload["dimensions"] == {
        "faithfulness": 90,
        "coverage": 80,
        "clarity": 70,
        "concision": 60,
    }
    assert evaluation.payload["evidence"] == ["Industrial output rose."]
    assert evaluation.payload["issues"] == ["The regional breakdown is omitted."]
    assert evaluation.payload["summary_extraction_id"] == str(extraction.id)
    assert evaluation.payload["summary_extractor"] == "llm_summary"
    assert evaluation.payload["raw_response"] == VALID_RESPONSE


def test_summary_quality_evaluator_records_provenance():
    article = _article()
    extraction = _summary_extraction(article)
    evaluator = LLMSummaryQualityEvaluator(
        FakeLLMProvider(response_text=VALID_RESPONSE, model="fake-quality-model")
    )

    evaluation = evaluator.evaluate(article, [extraction])

    assert evaluation.payload["metadata"] == {
        "generated_by": "llm",
        "provider": "fake",
        "model": "fake-quality-model",
        "prompt_version": SUMMARY_QUALITY_PROMPT_VERSION,
    }


def test_summary_quality_evaluator_uses_configured_summary_extractor():
    article = _article()
    ignored = _summary_extraction(article)
    selected = _summary_extraction(article, extractor="local_summary")
    provider = FakeLLMProvider(response_text=VALID_RESPONSE)
    evaluator = LLMSummaryQualityEvaluator(
        provider,
        criterion="newsletter_summary_quality",
        summary_extractor="local_summary",
    )

    evaluation = evaluator.evaluate(article, [ignored, selected])

    assert evaluation.criterion == "newsletter_summary_quality"
    assert evaluation.payload["summary_extraction_id"] == str(selected.id)
    assert evaluation.payload["summary_extractor"] == "local_summary"


def test_summary_quality_evaluator_requires_configured_summary_extraction():
    article = _article()
    evaluator = LLMSummaryQualityEvaluator(
        FakeLLMProvider(response_text=VALID_RESPONSE),
        summary_extractor="local_summary",
    )

    with pytest.raises(ValueError, match="requires a summary extraction"):
        evaluator.evaluate(article, [_summary_extraction(article)])


@pytest.mark.parametrize("summary", [None, "", "   ", ["not", "text"]])
def test_summary_quality_evaluator_requires_non_empty_summary(summary):
    article = _article()
    evaluator = LLMSummaryQualityEvaluator(
        FakeLLMProvider(response_text=VALID_RESPONSE)
    )

    with pytest.raises(ValueError, match="requires a non-empty summary"):
        evaluator.evaluate(article, [_summary_extraction(article, summary=summary)])


def test_summary_quality_evaluator_rejects_invalid_json():
    article = _article()
    evaluator = LLMSummaryQualityEvaluator(FakeLLMProvider(response_text="not json"))

    with pytest.raises(ValueError, match="valid JSON"):
        evaluator.evaluate(article, [_summary_extraction(article)])


@pytest.mark.parametrize(
    "response",
    [
        VALID_RESPONSE.replace('"faithfulness": 90', '"faithfulness": -1'),
        VALID_RESPONSE.replace('"coverage": 80', '"coverage": 101'),
        VALID_RESPONSE.replace('"clarity": 70', '"clarity": "70"'),
        VALID_RESPONSE.replace('"concision": 60, ', ""),
        VALID_RESPONSE.replace('"confidence": 0.85', '"confidence": 2'),
        VALID_RESPONSE.replace(
            '"rationale": "Accurate and clear, with one omitted detail."',
            '"rationale": ""',
        ),
        VALID_RESPONSE.replace(
            '"evidence": ["Industrial output rose."]',
            '"evidence": "Industrial output rose."',
        ),
        VALID_RESPONSE.replace(
            '"issues": ["The regional breakdown is omitted."]',
            '"issues": [3]',
        ),
    ],
)
def test_summary_quality_evaluator_rejects_invalid_response_fields(response):
    article = _article()
    evaluator = LLMSummaryQualityEvaluator(FakeLLMProvider(response_text=response))

    with pytest.raises(ValueError):
        evaluator.evaluate(article, [_summary_extraction(article)])


def test_build_summary_quality_evaluator_with_nested_fake_provider():
    config = ProcessorConfig(
        type="llm_summary_quality",
        name="Summary quality",
        settings={
            "summary_extractor": "local_summary",
            "criterion": "newsletter_summary_quality",
            "provider": {
                "type": "fake",
                "response_text": VALID_RESPONSE,
                "model": "fake-quality-model",
            },
        },
    )

    evaluator = build_evaluator(config)

    assert isinstance(evaluator, LLMSummaryQualityEvaluator)
    assert evaluator.display_name == "Summary quality"
    assert evaluator.summary_extractor == "local_summary"
    assert evaluator.criterion == "newsletter_summary_quality"
    assert evaluator.provider.name == "fake"
    assert evaluator.provider.model == "fake-quality-model"


def test_build_summary_quality_evaluator_with_ollama_provider():
    config = ProcessorConfig(
        type="llm_summary_quality",
        settings={
            "provider": {
                "type": "ollama",
                "model": "qwen3.5:9b",
                "base_url": "http://ollama.test:11434",
                "temperature": 0,
                "max_tokens": 300,
            }
        },
    )

    evaluator = build_evaluator(config)

    assert isinstance(evaluator, LLMSummaryQualityEvaluator)
    assert isinstance(evaluator.provider, OllamaProvider)
    assert evaluator.provider.config.model == "qwen3.5:9b"
    assert evaluator.provider.config.base_url == "http://ollama.test:11434"
    assert evaluator.provider.config.temperature == 0
    assert evaluator.provider.config.max_tokens == 300


def test_build_summary_quality_evaluator_with_openai_provider(monkeypatch):
    RecordingOpenAI.calls = []
    monkeypatch.setenv("EDITORIAL_OPENAI_KEY", "secret-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=RecordingOpenAI))
    config = ProcessorConfig(
        type="llm_summary_quality",
        settings={
            "provider": {
                "type": "openai",
                "model": "gpt-test",
                "api_key_env": "EDITORIAL_OPENAI_KEY",
                "base_url": "https://example.test/v1",
                "temperature": 0.1,
                "max_tokens": 300,
            }
        },
    )

    evaluator = build_evaluator(config)

    assert isinstance(evaluator, LLMSummaryQualityEvaluator)
    assert isinstance(evaluator.provider, OpenAIProvider)
    assert RecordingOpenAI.calls == [
        {"api_key": "secret-key", "base_url": "https://example.test/v1"}
    ]
    assert RecordingOpenAI.responses is not None
    article = _article()
    evaluator.evaluate(article, [_summary_extraction(article)])
    request = RecordingOpenAI.responses.calls[0]
    assert request["model"] == "gpt-test"
    assert request["temperature"] == 0.1
    assert request["max_output_tokens"] == 300


def test_nested_provider_config_also_works_for_llm_relevance():
    config = ProcessorConfig(
        type="llm_relevance",
        settings={
            "provider": {
                "type": "fake",
                "response_text": (
                    '{"score": 75, "confidence": 0.8, "rationale": "Relevant."}'
                ),
                "model": "fake-relevance-model",
            }
        },
    )

    evaluator = build_evaluator(config)
    evaluation = evaluator.evaluate(_article(), [])

    assert evaluation.score == 75
    assert evaluation.payload["metadata"]["model"] == "fake-relevance-model"


def test_cli_evaluate_runs_configured_summary_quality_evaluator(tmp_path):
    db_path = tmp_path / "test.sqlite"
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(
        f"""
publication:
  name: Summary Quality Test
evaluators:
  - type: llm_summary_quality
    name: Summary quality
    summary_extractor: llm_summary
    provider:
      type: fake
      model: fake-quality-model
      response_text: >-
        {VALID_RESPONSE}
""",
        encoding="utf-8",
    )
    article = _article()
    SQLiteArticleRepository(db_path).upsert(article)
    SQLiteExtractionRepository(db_path).insert(_summary_extraction(article))

    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "Stored evaluations: 1" in result.stdout
    evaluations = SQLiteEvaluationRepository(db_path).list()
    assert len(evaluations) == 1
    assert evaluations[0].kind == "summary_quality"
    assert evaluations[0].score == 75
    assert evaluations[0].payload["metadata"]["provider"] == "fake"

    inspection = CliRunner().invoke(
        app,
        [
            "evaluation",
            "show",
            str(evaluations[0].id),
            "--db",
            str(db_path),
        ],
    )
    assert inspection.exit_code == 0
    assert "Dimensions" in inspection.stdout
    assert "Faithfulness" in inspection.stdout
    assert "Issues" in inspection.stdout
    assert "Summary extractor" in inspection.stdout
