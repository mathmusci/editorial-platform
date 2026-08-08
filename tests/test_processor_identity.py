import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from editorial.cli import app
from editorial.config import load_publication_config
from editorial.config.models import ProcessorConfig
from editorial.engine import EditorialEngine
from editorial.evaluators import build_evaluator, describe_evaluator
from editorial.extractors import build_extractor, describe_extractor
from editorial.models import Article
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


QUALITY_A = (
    '{"faithfulness": 90, "coverage": 80, "clarity": 70, '
    '"concision": 60, "confidence": 0.8, "rationale": "Quality A.", '
    '"evidence": [], "issues": []}'
)
QUALITY_B = (
    '{"faithfulness": 80, "coverage": 70, "clarity": 60, '
    '"concision": 50, "confidence": 0.7, "rationale": "Quality B.", '
    '"evidence": [], "issues": ["Missing detail."]}'
)


def _summary_config(key: str, name: str, response_text: str) -> ProcessorConfig:
    return ProcessorConfig(
        type="llm_summary",
        key=key,
        name=name,
        settings={
            "provider": {
                "type": "fake",
                "model": f"{key}-model",
                "response_text": response_text,
            }
        },
    )


def _quality_config(
    key: str,
    name: str,
    summary_extractor: str,
    response_text: str,
) -> ProcessorConfig:
    return ProcessorConfig(
        type="llm_summary_quality",
        key=key,
        name=name,
        settings={
            "summary_extractor": summary_extractor,
            "provider": {
                "type": "fake",
                "model": "quality-judge",
                "response_text": response_text,
            },
        },
    )


def test_load_processor_key_as_top_level_configuration(tmp_path):
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(
        """
publication:
  name: Identity test
extractors:
  - type: llm_summary
    key: summary_qwen
    name: Qwen summary
    provider:
      type: fake
      response_text: Test summary
""",
        encoding="utf-8",
    )

    config = load_publication_config(config_path)

    assert config.extractors[0].key == "summary_qwen"
    assert "key" not in config.extractors[0].settings


@pytest.mark.parametrize("key", ["", "has spaces", "-leading", "punctuation!"])
def test_processor_key_must_be_a_non_empty_machine_identifier(key):
    with pytest.raises(ValidationError):
        ProcessorConfig(type="reading_time", key=key)


def test_extractor_key_controls_descriptor_progress_and_stored_identity():
    config = _summary_config("summary_qwen", "Qwen summary", "Qwen output.")
    extractor = build_extractor(config)
    article = Article(title="Industrial output")

    descriptor = describe_extractor(config)
    extraction = extractor.extract(article)

    assert extractor.name == "summary_qwen"
    assert extractor.display_name == "Qwen summary"
    assert descriptor.key == "summary_qwen"
    assert descriptor.display_name == "Qwen summary"
    assert extraction.extractor == "summary_qwen"


def test_evaluator_key_controls_stored_identity():
    article = Article(title="Industrial output", content="Output increased.")
    extraction = build_extractor(
        _summary_config("summary_qwen", "Qwen summary", "Output increased.")
    ).extract(article)
    evaluator = build_evaluator(
        _quality_config(
            "quality_qwen",
            "Qwen summary quality",
            "summary_qwen",
            QUALITY_A,
        )
    )
    descriptor = describe_evaluator(
        _quality_config(
            "quality_qwen",
            "Qwen summary quality",
            "summary_qwen",
            QUALITY_A,
        )
    )

    evaluation = evaluator.evaluate(article, [extraction])

    assert evaluator.name == "quality_qwen"
    assert evaluator.display_name == "Qwen summary quality"
    assert descriptor.key == "quality_qwen"
    assert descriptor.display_name == "Qwen summary quality"
    assert descriptor.kind == "summary_quality"
    assert evaluation.evaluator == "quality_qwen"
    assert evaluation.payload["summary_extractor"] == "summary_qwen"


def test_multiple_summary_models_and_evaluators_coexist_and_resume(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repository = SQLiteArticleRepository(db_path)
    extraction_repository = SQLiteExtractionRepository(db_path)
    evaluation_repository = SQLiteEvaluationRepository(db_path)
    article_repository.upsert(
        Article(title="Industrial output", content="Industrial output increased.")
    )
    engine = EditorialEngine(
        article_repository,
        extraction_repository,
        evaluation_repository,
    )
    extractors = [
        build_extractor(
            _summary_config("summary_qwen", "Qwen summary", "Qwen output.")
        ),
        build_extractor(
            _summary_config("summary_llama", "Llama summary", "Llama output.")
        ),
    ]
    evaluators = [
        build_evaluator(
            _quality_config(
                "quality_qwen",
                "Qwen summary quality",
                "summary_qwen",
                QUALITY_A,
            )
        ),
        build_evaluator(
            _quality_config(
                "quality_llama",
                "Llama summary quality",
                "summary_llama",
                QUALITY_B,
            )
        ),
    ]

    extraction_result = engine.extract(extractors)
    evaluation_result = engine.evaluate(evaluators)
    resumed_extraction = engine.extract(extractors, missing_only=True)
    resumed_evaluation = engine.evaluate(evaluators, missing_only=True)

    assert extraction_result.stored == 2
    assert evaluation_result.stored == 2
    assert resumed_extraction.skipped == 2
    assert resumed_evaluation.skipped == 2
    assert {item.extractor for item in extraction_repository.list()} == {
        "summary_qwen",
        "summary_llama",
    }
    evaluations = evaluation_repository.list()
    assert {item.evaluator for item in evaluations} == {
        "quality_qwen",
        "quality_llama",
    }
    assert {item.score for item in evaluations} == {75, 65}


def test_cli_runs_multiple_keyed_summary_pipelines_in_one_database(tmp_path):
    db_path = tmp_path / "test.sqlite"
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(
        f"""
publication:
  name: Model comparison
extractors:
  - type: llm_summary
    key: summary_a
    provider:
      type: fake
      response_text: Summary A.
  - type: llm_summary
    key: summary_b
    provider:
      type: fake
      response_text: Summary B.
evaluators:
  - type: llm_summary_quality
    key: quality_a
    summary_extractor: summary_a
    provider:
      type: fake
      response_text: >-
        {QUALITY_A}
  - type: llm_summary_quality
    key: quality_b
    summary_extractor: summary_b
    provider:
      type: fake
      response_text: >-
        {QUALITY_B}
""",
        encoding="utf-8",
    )
    SQLiteArticleRepository(db_path).upsert(
        Article(title="Industrial output", content="Industrial output increased.")
    )
    runner = CliRunner()

    extraction = runner.invoke(
        app,
        ["extract", "--config", str(config_path), "--db", str(db_path)],
    )
    evaluation = runner.invoke(
        app,
        ["evaluate", "--config", str(config_path), "--db", str(db_path)],
    )
    resumed = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--missing-only",
        ],
    )

    assert extraction.exit_code == 0
    assert "Stored extractions: 2" in extraction.stdout
    assert evaluation.exit_code == 0
    assert "Stored evaluations: 2" in evaluation.stdout
    assert resumed.exit_code == 0
    assert "Skipped: 2" in resumed.stdout
    assert SQLiteExtractionRepository(db_path).count() == 2
    assert SQLiteEvaluationRepository(db_path).count() == 2


def test_engine_rejects_duplicate_extractor_keys_before_processing(tmp_path):
    engine = EditorialEngine(
        SQLiteArticleRepository(tmp_path / "test.sqlite"),
        SQLiteExtractionRepository(tmp_path / "test.sqlite"),
    )
    extractors = [
        build_extractor(ProcessorConfig(type="reading_time")),
        build_extractor(ProcessorConfig(type="reading_time")),
    ]

    with pytest.raises(ValueError, match="duplicate keys: 'reading_time'"):
        engine.extract(extractors)


def test_engine_rejects_duplicate_evaluator_keys_before_processing(tmp_path):
    db_path = tmp_path / "test.sqlite"
    engine = EditorialEngine(
        SQLiteArticleRepository(db_path),
        SQLiteExtractionRepository(db_path),
        SQLiteEvaluationRepository(db_path),
    )
    evaluators = [
        build_evaluator(ProcessorConfig(type="rule_relevance")),
        build_evaluator(ProcessorConfig(type="rule_relevance")),
    ]

    with pytest.raises(ValueError, match="duplicate keys: 'rule_relevance'"):
        engine.evaluate(evaluators)
