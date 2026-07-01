from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import EvaluationInspectionService
from editorial.models import Article, Evaluation, Extraction, WorkflowEvent
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> EvaluationInspectionService:
    return EvaluationInspectionService(
        evaluations=SQLiteEvaluationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_evaluation(
    db_path,
    *,
    with_article: bool = True,
    with_extraction: bool = True,
    payload: dict | None = None,
) -> tuple[Evaluation, Article]:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
        summary="Useful statistics.",
    )
    evaluation = Evaluation(
        article_id=article.id,
        evaluator="rule_relevance",
        evaluator_version="0.1.0",
        kind="relevance",
        score=85,
        confidence=0.9,
        rationale="Matched include terms ['statistics'].",
        payload=payload or {"evidence": ["title"], "reasoning": "Strong match."},
    )

    if with_article:
        SQLiteArticleRepository(db_path).upsert(article)
    SQLiteEvaluationRepository(db_path).insert(evaluation)
    if with_extraction:
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="reading_time",
                extractor_version="0.1.0",
                kind="reading_time",
                payload={"reading_minutes": 4, "word_count": 700},
            )
        )
    return evaluation, article


def test_evaluation_inspection_service_builds_review_model(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, article = _store_evaluation(db_path)

    inspection = _service(db_path).get(evaluation.id)

    assert inspection is not None
    assert inspection.evaluation == evaluation
    assert inspection.article == article
    assert inspection.extractions[0].kind == "reading_time"
    assert inspection.payload_highlights["reasoning"] == "Strong match."
    assert inspection.payload_highlights["evidence"] == ["title"]


def test_cli_evaluation_list_discovers_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path)

    result = CliRunner().invoke(app, ["evaluation", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Evaluations" in result.stdout
    assert str(evaluation.id) in result.stdout
    assert "Industrial statistics" in result.stdout
    assert "rule_relevance" in result.stdout
    assert "relevance" in result.stdout


def test_cli_evaluation_show_displays_core_result_and_article_title(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path)

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "rule_relevance" in result.stdout
    assert "relevance" in result.stdout
    assert "85" in result.stdout
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout


def test_cli_evaluation_show_displays_rationale_and_confidence(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path)

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Matched include terms" in result.stdout
    assert "0.9" in result.stdout
    assert "Strong match." in result.stdout


def test_cli_evaluation_show_handles_missing_article_gracefully(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path, with_article=False)

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(evaluation.article_id) in result.stdout
    assert "not available" in result.stdout


def test_cli_evaluation_show_lists_related_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path)

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Related Extractions" in result.stdout
    assert "reading_time" in result.stdout
    assert "reading_minutes" in result.stdout


def test_cli_evaluation_show_displays_ai_provenance_metadata(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(
        db_path,
        payload={
            "reasoning": "The article is relevant.",
            "metadata": {
                "generated_by": "llm",
                "provider": "fake",
                "model": "fake-relevance-model",
                "prompt_version": "relevance-v1",
            },
        },
    )

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "AI Provenance" in result.stdout
    assert "generated_by" in result.stdout
    assert "llm" in result.stdout
    assert "fake-relevance-model" in result.stdout
    assert "relevance-v1" in result.stdout


def test_cli_evaluation_show_includes_workflow_events(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article = _store_evaluation(db_path)
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="evaluation",
            artefact_id=evaluation.id,
            event_type="evaluation-reviewed",
            actor="Andy",
            reason="Looks plausible",
        )
    )

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "evaluation-reviewed" in result.stdout
    assert "Looks plausible" in result.stdout


def test_cli_evaluation_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation_id = uuid4()

    result = CliRunner().invoke(
        app, ["evaluation", "show", str(evaluation_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Evaluation not found: {evaluation_id}" in result.stdout
