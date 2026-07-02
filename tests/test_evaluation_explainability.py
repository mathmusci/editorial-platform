from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.explain import EvaluationExplanationService
from editorial.inspection import EvaluationInspectionService
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    PublicationSection,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteWorkflowEventRepository,
)


def _inspection_service(db_path) -> EvaluationInspectionService:
    return EvaluationInspectionService(
        evaluations=SQLiteEvaluationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _service(db_path) -> EvaluationExplanationService:
    return EvaluationExplanationService(
        evaluation_inspections=_inspection_service(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
    )


def _store_evaluation_fixture(
    db_path,
    *,
    ai: bool = False,
    rationale: str | None = "Matched include terms ['statistics'].",
    confidence: float | None = 0.9,
    with_evidence: bool = True,
    with_extractions: bool = True,
    with_related: bool = True,
) -> tuple[Evaluation, Article, IssueProposal | None, Publication | None]:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
        summary="Useful statistics.",
    )
    payload = {}
    if with_evidence:
        payload.update(
            {
                "reasoning": "Strong match with the publication brief.",
                "evidence": ["title", "summary"],
                "decision": "relevant",
            }
        )
    if ai:
        payload["metadata"] = {
            "generated_by": "llm",
            "provider": "fake",
            "model": "fake-relevance-model",
            "prompt_version": "relevance-v1",
            "token_usage": {"input": 10, "output": 5},
            "latency": 1.25,
            "cost": 0.01,
        }

    evaluation = Evaluation(
        article_id=article.id,
        evaluator="llm_relevance" if ai else "rule_relevance",
        evaluator_version="0.1.0",
        kind="relevance",
        score=82,
        confidence=confidence,
        rationale=rationale,
        payload=payload,
    )

    SQLiteArticleRepository(db_path).upsert(article)
    SQLiteEvaluationRepository(db_path).insert(evaluation)
    if with_extractions:
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="reading_time",
                extractor_version="0.1.0",
                kind="reading_time",
                payload={"reading_minutes": 4, "word_count": 700},
            )
        )
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="summary",
                extractor_version="0.1.0",
                kind="summary",
                payload={"summary": "A concise summary."},
            )
        )

    proposal = None
    publication = None
    if with_related:
        proposal = IssueProposal(
            optimiser="greedy",
            article_ids=[article.id],
            objective_value=80,
        )
        publication = Publication(
            proposal_id=proposal.id,
            title="BIS Newsletter",
            sections=[
                PublicationSection(
                    heading="Selected articles",
                    article_ids=[article.id],
                )
            ],
        )
        SQLiteIssueProposalRepository(db_path).insert(proposal)
        SQLitePublicationRepository(db_path).insert(publication)

    return evaluation, article, proposal, publication


def test_service_builds_deterministic_evaluator_explanation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, article, proposal, publication = _store_evaluation_fixture(db_path)

    explanation = _service(db_path).get(evaluation.id)

    assert explanation is not None
    assert explanation.evaluation_id == evaluation.id
    assert explanation.article_id == article.id
    assert explanation.created_at == evaluation.created_at
    assert explanation.article_title == "Industrial statistics"
    assert explanation.provenance.evaluator_type == "deterministic"
    assert "rule_relevance evaluator" in explanation.interpretation.summary
    assert explanation.related_proposals[0].proposal_id == proposal.id
    assert explanation.related_publications[0].publication_id == publication.id


def test_service_builds_ai_evaluator_explanation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path, ai=True
    )

    explanation = _service(db_path).get(evaluation.id)

    assert explanation is not None
    assert explanation.provenance.evaluator_type == "ai"
    assert explanation.provenance.fields["provider"] == "fake"
    assert explanation.provenance.fields["model"] == "fake-relevance-model"
    assert "AI evaluator" in explanation.interpretation.summary


def test_cli_explain_evaluation_works(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Evaluation Identity" in result.stdout
    assert "Outcome" in result.stdout
    assert "Interpretation" in result.stdout


def test_cli_output_includes_related_article(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, article, _proposal, _publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(article.id) in result.stdout
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout


def test_cli_output_reports_score_confidence_and_rationale(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "relevance score of 82.0 with confidence 0.9" in result.stdout
    assert "Matched include terms" in result.stdout
    assert "The stored confidence is 0.9" in result.stdout


def test_cli_output_reports_ai_provenance(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path, ai=True
    )

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Provenance" in result.stdout
    assert "generated_by" in result.stdout
    assert "llm" in result.stdout
    assert "fake-relevance-model" in result.stdout
    assert "relevance-v1" in result.stdout
    assert "token_usage" in result.stdout


def test_cli_output_reports_missing_provenance(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No provenance recorded." in result.stdout


def test_cli_output_reports_missing_rationale(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path, rationale=None, with_evidence=False
    )

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No rationale or reasoning was recorded." in result.stdout


def test_cli_output_reports_missing_confidence(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path, confidence=None
    )

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Confidence unavailable." in result.stdout


def test_cli_output_reports_missing_evidence(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path,
        rationale=None,
        with_evidence=False,
        with_extractions=False,
    )

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No evidence recorded." in result.stdout
    assert "No evaluation evidence was recorded." in result.stdout
    assert "No related extractions were recorded." in result.stdout


def test_cli_output_shows_related_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "reading_time" in result.stdout
    assert "reading_minutes" in result.stdout
    assert "summary" in result.stdout


def test_cli_output_shows_related_proposals_and_publications(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, proposal, publication = _store_evaluation_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(proposal.id) in result.stdout
    assert str(publication.id) in result.stdout
    assert "BIS Newsletter" in result.stdout


def test_cli_output_does_not_imply_unrecorded_reasoning(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation, _article, _proposal, _publication = _store_evaluation_fixture(
        db_path, ai=True
    )

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "The model believed" not in result.stdout
    assert "The evaluator chose" not in result.stdout
    assert "The AI decided" not in result.stdout


def test_cli_invalid_evaluation_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    evaluation_id = uuid4()

    result = CliRunner().invoke(
        app, ["explain", "evaluation", str(evaluation_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Evaluation not found: {evaluation_id}" in result.stdout
