from datetime import UTC, datetime
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import SummaryQualityComparisonService
from editorial.models import Article, Evaluation, Extraction
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


def _service(db_path) -> SummaryQualityComparisonService:
    return SummaryQualityComparisonService(
        evaluations=SQLiteEvaluationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
    )


def _article(title: str, day: int) -> Article:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return Article(title=title, created_at=created_at, updated_at=created_at)


def _quality_evaluation(
    article: Article,
    evaluator: str,
    *,
    score: float,
    confidence: float,
    faithfulness: float,
    coverage: float,
    clarity: float,
    concision: float,
    issues: list[str] | None = None,
    model: str,
    summary_extraction: Extraction,
) -> Evaluation:
    return Evaluation(
        article_id=article.id,
        evaluator=evaluator,
        evaluator_version="0.1.0",
        kind="summary_quality",
        criterion="summary_quality",
        score=score,
        confidence=confidence,
        rationale="Stored quality assessment.",
        payload={
            "dimensions": {
                "faithfulness": faithfulness,
                "coverage": coverage,
                "clarity": clarity,
                "concision": concision,
            },
            "issues": issues or [],
            "summary_extraction_id": str(summary_extraction.id),
            "summary_extractor": summary_extraction.extractor,
            "metadata": {
                "provider": "ollama",
                "model": model,
                "prompt_version": "summary-quality-v1",
            },
        },
    )


def _store_comparison_fixture(db_path) -> tuple[Article, Article, Article]:
    oldest = _article("Oldest, no evaluations", 1)
    middle = _article("Middle, partial evaluations", 2)
    newest = _article("Newest, complete evaluations", 3)
    article_repository = SQLiteArticleRepository(db_path)
    for article in (oldest, middle, newest):
        article_repository.upsert(article)

    evaluation_repository = SQLiteEvaluationRepository(db_path)
    extraction_repository = SQLiteExtractionRepository(db_path)
    newest_qwen = _summary_extraction(newest, "summary_qwen", "qwen3.5:9b")
    middle_qwen = _summary_extraction(middle, "summary_qwen", "qwen3.5:9b")
    newest_llama = _summary_extraction(newest, "summary_llama", "llama3.2")
    for extraction in (newest_qwen, middle_qwen, newest_llama):
        extraction_repository.insert(extraction)
    evaluation_repository.insert(
        _quality_evaluation(
            newest,
            "quality_qwen",
            score=80,
            confidence=0.9,
            faithfulness=90,
            coverage=80,
            clarity=70,
            concision=80,
            issues=["One detail omitted."],
            model="quality-judge",
            summary_extraction=newest_qwen,
        )
    )
    evaluation_repository.insert(
        _quality_evaluation(
            middle,
            "quality_qwen",
            score=60,
            confidence=0.7,
            faithfulness=70,
            coverage=60,
            clarity=50,
            concision=60,
            model="quality-judge",
            summary_extraction=middle_qwen,
        )
    )
    evaluation_repository.insert(
        _quality_evaluation(
            newest,
            "quality_llama",
            score=70,
            confidence=0.8,
            faithfulness=80,
            coverage=70,
            clarity=60,
            concision=70,
            issues=["Opening is wordy.", "One detail omitted."],
            model="quality-judge",
            summary_extraction=newest_llama,
        )
    )
    return oldest, middle, newest


def _summary_extraction(
    article: Article,
    extractor: str,
    model: str,
) -> Extraction:
    return Extraction(
        article_id=article.id,
        extractor=extractor,
        kind="summary",
        payload={
            "summary": "Stored summary.",
            "metadata": {
                "provider": "ollama",
                "model": model,
                "prompt_version": "summary-v1",
            },
        },
    )


def test_comparison_reports_aggregate_scores_coverage_and_provenance(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_comparison_fixture(db_path)

    report = _service(db_path).compare(evaluator_keys=["quality_qwen", "quality_llama"])

    assert report.articles_selected == 3
    assert report.expected_evaluations == 6
    assert report.present == 3
    assert report.missing == 3
    qwen, llama = report.aggregates
    assert qwen.evaluator == "quality_qwen"
    assert qwen.evaluated == 2
    assert qwen.missing == 1
    assert qwen.average_score == 70
    assert qwen.average_confidence == 0.8
    assert qwen.average_dimensions.model_dump() == {
        "faithfulness": 80,
        "coverage": 70,
        "clarity": 60,
        "concision": 70,
    }
    assert qwen.issue_count == 1
    assert qwen.summary_providers == ["ollama"]
    assert qwen.summary_models == ["qwen3.5:9b"]
    assert qwen.evaluator_providers == ["ollama"]
    assert qwen.evaluator_models == ["quality-judge"]
    assert llama.evaluated == 1
    assert llama.missing == 2
    assert llama.average_score == 70
    assert llama.issue_count == 2


def test_comparison_reports_each_article_and_missing_results(tmp_path):
    db_path = tmp_path / "test.sqlite"
    oldest, middle, newest = _store_comparison_fixture(db_path)

    report = _service(db_path).compare(evaluator_keys=["quality_qwen", "quality_llama"])

    assert [item.article_id for item in report.articles] == [
        newest.id,
        middle.id,
        oldest.id,
    ]
    complete = report.articles[0]
    assert [item.status for item in complete.results] == ["present", "present"]
    assert complete.results[0].dimensions.faithfulness == 90
    assert complete.results[0].issues == ["One detail omitted."]
    assert complete.results[0].summary_extractor == "summary_qwen"
    assert complete.results[0].summary_model == "qwen3.5:9b"
    assert complete.results[0].evaluator_model == "quality-judge"
    partial = report.articles[1]
    assert [item.status for item in partial.results] == ["present", "missing"]
    missing = report.articles[2]
    assert [item.status for item in missing.results] == ["missing", "missing"]


def test_comparison_discovers_stored_summary_quality_evaluators(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_comparison_fixture(db_path)
    SQLiteEvaluationRepository(db_path).insert(
        Evaluation(
            article_id=_article("Unstored article", 4).id,
            evaluator="rule_relevance",
            kind="relevance",
            score=90,
        )
    )

    report = _service(db_path).compare()

    assert report.evaluator_keys == ["quality_llama", "quality_qwen"]


def test_comparison_applies_article_selection_before_limit_and_offset(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _oldest, middle, _newest = _store_comparison_fixture(db_path)

    report = _service(db_path).compare(
        evaluator_keys=["quality_qwen", "quality_llama"],
        limit=1,
        offset=1,
    )

    assert report.articles_selected == 1
    assert report.articles[0].article_id == middle.id
    assert report.present == 1
    assert report.missing == 1


def test_comparison_can_select_known_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    oldest, _middle, newest = _store_comparison_fixture(db_path)

    report = _service(db_path).compare(
        evaluator_keys=["quality_qwen", "quality_llama"],
        article_ids=[oldest.id, newest.id],
    )

    assert [item.article_id for item in report.articles] == [newest.id, oldest.id]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be a positive integer"),
        ({"offset": -1}, "offset must be zero or greater"),
        (
            {"evaluator_keys": ["quality_qwen"]},
            "requires at least two evaluator keys",
        ),
        (
            {"evaluator_keys": ["quality_qwen", "quality_qwen"]},
            "Duplicate evaluator keys",
        ),
    ],
)
def test_comparison_rejects_invalid_selection(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        _service(tmp_path / "test.sqlite").compare(**kwargs)


def test_comparison_reports_missing_article_id(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_comparison_fixture(db_path)
    missing_id = uuid4()

    with pytest.raises(ValueError, match=str(missing_id)):
        _service(db_path).compare(
            evaluator_keys=["quality_qwen", "quality_llama"],
            article_ids=[missing_id],
        )


def test_comparison_tolerates_incomplete_legacy_payloads(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("Legacy evaluation", 1)
    SQLiteArticleRepository(db_path).upsert(article)
    repository = SQLiteEvaluationRepository(db_path)
    for evaluator in ("quality_a", "quality_b"):
        repository.insert(
            Evaluation(
                article_id=article.id,
                evaluator=evaluator,
                kind="summary_quality",
                score=50,
                payload={"dimensions": "not structured", "issues": "unknown"},
            )
        )

    report = _service(db_path).compare()

    assert report.aggregates[0].average_score == 50
    assert report.aggregates[0].average_dimensions.faithfulness is None
    assert report.aggregates[0].issue_count == 0


def test_cli_evaluation_compare_renders_aggregate_and_article_results(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_comparison_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "compare",
            "--db",
            str(db_path),
            "--evaluator",
            "quality_qwen",
            "--evaluator",
            "quality_llama",
        ],
    )

    assert result.exit_code == 0
    assert "Summary Quality Comparison" in result.stdout
    assert "Aggregate Quality" in result.stdout
    assert "quality_qwen" in result.stdout
    assert "quality_llama" in result.stdout
    assert "quality-judge" in result.stdout
    assert "qwen3.5:9b" in result.stdout
    assert "llama3.2" in result.stdout
    assert "Summary model" in result.stdout
    assert "Evaluator model" in result.stdout
    assert "Faithfulness" in result.stdout
    assert "Content coverage" in result.stdout
    assert "One detail omitted." in result.stdout
    assert "missing" in result.stdout
    assert "Expected evaluations" in result.stdout
    assert "Present" in result.stdout


def test_cli_evaluation_compare_reports_insufficient_evaluators_cleanly(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "compare",
            "--db",
            str(tmp_path / "test.sqlite"),
        ],
    )

    assert result.exit_code != 0
    output = " ".join(result.output.replace("│", " ").split())
    assert "at least two evaluator keys" in output
