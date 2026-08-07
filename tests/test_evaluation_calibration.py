from datetime import UTC, datetime
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import (
    HumanSummaryQualityReferenceService,
    SummaryQualityCalibrationService,
)
from editorial.models import Article, Evaluation, Extraction
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


def _reference_service(db_path) -> HumanSummaryQualityReferenceService:
    return HumanSummaryQualityReferenceService(
        evaluations=SQLiteEvaluationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
    )


def _calibration_service(db_path) -> SummaryQualityCalibrationService:
    return SummaryQualityCalibrationService(
        evaluations=SQLiteEvaluationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
    )


def _article(title: str, day: int) -> Article:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return Article(title=title, created_at=created_at, updated_at=created_at)


def _summary(article: Article, extractor: str = "summary_qwen") -> Extraction:
    return Extraction(
        article_id=article.id,
        extractor=extractor,
        kind="summary",
        payload={
            "summary": "Industrial output increased.",
            "metadata": {"provider": "ollama", "model": "qwen3.5:9b"},
        },
    )


def _store_article_and_summary(
    db_path,
    article: Article,
    extractor: str = "summary_qwen",
) -> Extraction:
    SQLiteArticleRepository(db_path).upsert(article)
    extraction = _summary(article, extractor)
    SQLiteExtractionRepository(db_path).insert(extraction)
    return extraction


def _record_reference(
    db_path,
    article: Article,
    extraction: Extraction,
    *,
    evaluator: str = "human_qwen",
    scores: tuple[float, float, float, float] = (90, 80, 70, 60),
) -> Evaluation:
    return _reference_service(db_path).record(
        article_id=article.id,
        summary_extraction_id=extraction.id,
        evaluator=evaluator,
        reviewer="Editor",
        faithfulness=scores[0],
        coverage=scores[1],
        clarity=scores[2],
        concision=scores[3],
        confidence=0.9,
        rationale="Compared carefully with the source article.",
        evidence=["The central claim is supported."],
        issues=["One detail is missing."],
    )


def _candidate(
    article: Article,
    extraction_id,
    *,
    scores: tuple[float, float, float, float],
) -> Evaluation:
    dimensions = dict(
        zip(
            ("faithfulness", "coverage", "clarity", "concision"),
            scores,
            strict=True,
        )
    )
    return Evaluation(
        article_id=article.id,
        evaluator="quality_qwen",
        kind="summary_quality",
        score=round(sum(scores) / 4, 2),
        confidence=0.8,
        payload={
            "dimensions": dimensions,
            "summary_extraction_id": (
                str(extraction_id) if extraction_id is not None else None
            ),
            "metadata": {
                "generated_by": "llm",
                "provider": "ollama",
                "model": "quality-judge",
            },
        },
    )


def test_record_human_reference_stores_scores_lineage_and_reviewer(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("Reference article", 1)
    extraction = _store_article_and_summary(db_path, article)

    evaluation = _record_reference(db_path, article, extraction)

    assert evaluation.evaluator == "human_qwen"
    assert evaluation.evaluator_version == "human-v1"
    assert evaluation.kind == "summary_quality"
    assert evaluation.score == 75
    assert evaluation.confidence == 0.9
    assert evaluation.payload["dimensions"] == {
        "faithfulness": 90,
        "coverage": 80,
        "clarity": 70,
        "concision": 60,
    }
    assert evaluation.payload["summary_extraction_id"] == str(extraction.id)
    assert evaluation.payload["summary_extractor"] == "summary_qwen"
    assert evaluation.payload["metadata"] == {
        "generated_by": "human",
        "reviewer": "Editor",
    }
    assert SQLiteEvaluationRepository(db_path).get(evaluation.id) == evaluation


def test_record_human_reference_replaces_same_article_and_key(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("Reference article", 1)
    extraction = _store_article_and_summary(db_path, article)

    first = _record_reference(db_path, article, extraction)
    second = _record_reference(
        db_path,
        article,
        extraction,
        scores=(100, 100, 100, 100),
    )

    assert first.id != second.id
    assert SQLiteEvaluationRepository(db_path).count() == 1
    assert SQLiteEvaluationRepository(db_path).list()[0].score == 100


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"evaluator": "has spaces"}, "Evaluator key"),
        ({"reviewer": " "}, "Reviewer"),
        ({"rationale": ""}, "Rationale"),
        ({"faithfulness": -1}, "Faithfulness"),
        ({"coverage": 101}, "Coverage"),
        ({"confidence": 2}, "Confidence"),
        ({"issues": [""]}, "Issue"),
    ],
)
def test_record_human_reference_validates_editorial_input(tmp_path, changes, message):
    db_path = tmp_path / "test.sqlite"
    article = _article("Reference article", 1)
    extraction = _store_article_and_summary(db_path, article)
    arguments = {
        "article_id": article.id,
        "summary_extraction_id": extraction.id,
        "evaluator": "human_qwen",
        "reviewer": "Editor",
        "faithfulness": 90,
        "coverage": 80,
        "clarity": 70,
        "concision": 60,
        "rationale": "Careful assessment.",
        "confidence": 0.9,
        "issues": [],
    }
    arguments.update(changes)

    with pytest.raises(ValueError, match=message):
        _reference_service(db_path).record(**arguments)


def test_record_human_reference_requires_matching_summary_extraction(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("Reference article", 1)
    other = _article("Other article", 2)
    SQLiteArticleRepository(db_path).upsert(article)
    extraction = _store_article_and_summary(db_path, other)

    with pytest.raises(ValueError, match="does not belong"):
        _reference_service(db_path).record(
            article_id=article.id,
            summary_extraction_id=extraction.id,
            evaluator="human_qwen",
            reviewer="Editor",
            faithfulness=90,
            coverage=80,
            clarity=70,
            concision=60,
            rationale="Careful assessment.",
        )


def _store_calibration_fixture(db_path):
    articles = [_article(f"Reference {index}", index) for index in range(1, 6)]
    evaluation_repository = SQLiteEvaluationRepository(db_path)
    extractions = []
    for article in articles:
        extraction = _store_article_and_summary(db_path, article)
        extractions.append(extraction)
        _record_reference(
            db_path,
            article,
            extraction,
            scores=(90, 80, 70, 60) if article == articles[0] else (60, 60, 60, 60),
        )

    evaluation_repository.insert(
        _candidate(articles[0], extractions[0].id, scores=(80, 90, 70, 50))
    )
    evaluation_repository.insert(
        _candidate(articles[1], extractions[1].id, scores=(70, 50, 65, 55))
    )
    different = _summary(articles[3], "summary_llama")
    SQLiteExtractionRepository(db_path).insert(different)
    evaluation_repository.insert(
        _candidate(articles[3], different.id, scores=(60, 60, 60, 60))
    )
    evaluation_repository.insert(_candidate(articles[4], None, scores=(60, 60, 60, 60)))
    return articles, extractions


def test_calibration_reports_coverage_and_agreement_metrics(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_calibration_fixture(db_path)

    report = _calibration_service(db_path).calibrate(
        reference_evaluator="human_qwen",
        candidate_evaluator="quality_qwen",
        tolerance=5,
    )

    assert report.references_selected == 5
    assert report.matched == 2
    assert report.missing_candidate == 1
    assert report.different_summary == 1
    assert report.unverifiable_summary == 1
    assert report.candidate_providers == ["ollama"]
    assert report.candidate_models == ["quality-judge"]
    assert report.metrics.mean_absolute_error == 1.25
    assert report.metrics.mean_error == -1.25
    assert report.metrics.within_tolerance == 2
    assert report.metrics.compared_scores == 2
    assert report.metrics.within_tolerance_percentage == 100
    assert report.metrics.dimension_mean_absolute_error.model_dump() == {
        "faithfulness": 10,
        "coverage": 10,
        "clarity": 2.5,
        "concision": 7.5,
    }


def test_calibration_reports_per_article_deltas_and_lineage_failures(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extractions = _store_calibration_fixture(db_path)

    report = _calibration_service(db_path).calibrate(
        reference_evaluator="human_qwen",
        candidate_evaluator="quality_qwen",
    )

    assert [item.article_id for item in report.articles] == list(
        reversed([article.id for article in articles])
    )
    by_article = {item.article_id: item for item in report.articles}
    first = by_article[articles[0].id]
    assert first.status == "matched"
    assert first.summary_extraction_id == extractions[0].id
    assert first.reference_score == 75
    assert first.candidate_score == 72.5
    assert first.score_delta == -2.5
    assert first.dimension_deltas.faithfulness == -10
    assert by_article[articles[2].id].status == "missing_candidate"
    assert by_article[articles[3].id].status == "different_summary"
    assert by_article[articles[4].id].status == "unverifiable_summary"


def test_calibration_selection_uses_reference_set_order(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, _extractions = _store_calibration_fixture(db_path)

    report = _calibration_service(db_path).calibrate(
        reference_evaluator="human_qwen",
        candidate_evaluator="quality_qwen",
        offset=1,
        limit=1,
    )

    assert report.references_selected == 1
    assert report.articles[0].article_id == articles[3].id


def test_calibration_rejects_non_human_reference_evaluator(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("AI evaluation", 1)
    extraction = _store_article_and_summary(db_path, article)
    SQLiteEvaluationRepository(db_path).insert(
        _candidate(article, extraction.id, scores=(80, 80, 80, 80))
    )

    with pytest.raises(ValueError, match="not recorded as human"):
        _calibration_service(db_path).calibrate(
            reference_evaluator="quality_qwen",
            candidate_evaluator="another_evaluator",
        )


def test_calibration_rejects_reference_to_missing_summary_extraction(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("Missing summary", 1)
    SQLiteArticleRepository(db_path).upsert(article)
    missing_extraction_id = uuid4()
    SQLiteEvaluationRepository(db_path).insert(
        Evaluation(
            article_id=article.id,
            evaluator="human_qwen",
            kind="summary_quality",
            score=75,
            payload={
                "summary_extraction_id": str(missing_extraction_id),
                "metadata": {"generated_by": "human", "reviewer": "Editor"},
            },
        )
    )

    with pytest.raises(ValueError, match=str(missing_extraction_id)):
        _calibration_service(db_path).calibrate(
            reference_evaluator="human_qwen",
            candidate_evaluator="quality_qwen",
        )


def test_calibration_rejects_missing_reference_and_invalid_options(tmp_path):
    service = _calibration_service(tmp_path / "test.sqlite")

    with pytest.raises(ValueError, match="must differ"):
        service.calibrate(
            reference_evaluator="same",
            candidate_evaluator="same",
        )
    with pytest.raises(ValueError, match="tolerance"):
        service.calibrate(
            reference_evaluator="human",
            candidate_evaluator="candidate",
            tolerance=-1,
        )
    with pytest.raises(ValueError, match="tolerance"):
        service.calibrate(
            reference_evaluator="human",
            candidate_evaluator="candidate",
            tolerance=float("nan"),
        )
    with pytest.raises(ValueError, match="No summary-quality references"):
        service.calibrate(
            reference_evaluator="human",
            candidate_evaluator="candidate",
        )


def test_cli_records_reference_and_renders_calibration(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _article("CLI reference", 1)
    extraction = _store_article_and_summary(db_path, article)
    runner = CliRunner()

    recorded = runner.invoke(
        app,
        [
            "evaluation",
            "record-reference",
            str(article.id),
            "--summary-extraction-id",
            str(extraction.id),
            "--evaluator",
            "human_qwen",
            "--reviewer",
            "Editor",
            "--faithfulness",
            "90",
            "--coverage",
            "80",
            "--clarity",
            "70",
            "--concision",
            "60",
            "--rationale",
            "Careful assessment.",
            "--issue",
            "One omission.",
            "--db",
            str(db_path),
        ],
    )
    SQLiteEvaluationRepository(db_path).insert(
        _candidate(article, extraction.id, scores=(80, 90, 70, 50))
    )
    calibrated = runner.invoke(
        app,
        [
            "evaluation",
            "calibrate",
            "--reference",
            "human_qwen",
            "--evaluator",
            "quality_qwen",
            "--tolerance",
            "5",
            "--db",
            str(db_path),
        ],
    )

    assert recorded.exit_code == 0
    assert "Human Summary-Quality Reference" in recorded.stdout
    assert "human_qwen" in recorded.stdout
    assert "75" in recorded.stdout
    assert calibrated.exit_code == 0
    assert "Summary Quality Calibration" in calibrated.stdout
    assert "Agreement" in calibrated.stdout
    assert "Mean absolute error" in calibrated.stdout
    assert "2.50" in calibrated.stdout
    assert "quality-judge" in calibrated.stdout
    assert "matched" in calibrated.stdout


def test_cli_record_reference_reports_missing_article_cleanly(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "record-reference",
            str(uuid4()),
            "--summary-extraction-id",
            str(uuid4()),
            "--evaluator",
            "human_qwen",
            "--reviewer",
            "Editor",
            "--faithfulness",
            "90",
            "--coverage",
            "80",
            "--clarity",
            "70",
            "--concision",
            "60",
            "--rationale",
            "Careful assessment.",
            "--db",
            str(tmp_path / "test.sqlite"),
        ],
    )

    assert result.exit_code != 0
    assert "Article not found" in result.output
