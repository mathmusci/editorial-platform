from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import ArticleInspectionService
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    PublicationSection,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> ArticleInspectionService:
    return ArticleInspectionService(
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        evaluations=SQLiteEvaluationRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_article(
    db_path,
    *,
    with_extraction: bool = True,
    with_evaluation: bool = True,
    with_ai_payloads: bool = False,
    with_proposal_publication: bool = False,
) -> Article:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
        authors=["A. Statistician"],
        summary="A short summary about industrial statistics.",
        content="Industrial statistics content. " * 40,
        metadata={"section_hint": "Industry"},
    )
    SQLiteArticleRepository(db_path).upsert(article)

    if with_extraction:
        payload = {"reading_minutes": 4, "word_count": 700}
        if with_ai_payloads:
            payload = {
                "summary": "AI generated summary",
                "metadata": {
                    "generated_by": "llm",
                    "provider": "fake",
                    "model": "fake-summary-model",
                    "prompt_version": "summary-v1",
                },
            }
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="llm_summary" if with_ai_payloads else "reading_time",
                extractor_version="0.1.0",
                kind="summary" if with_ai_payloads else "reading_time",
                payload=payload,
            )
        )

    if with_evaluation:
        payload = {}
        if with_ai_payloads:
            payload = {
                "metadata": {
                    "generated_by": "llm",
                    "provider": "fake",
                    "model": "fake-relevance-model",
                    "prompt_version": "relevance-v1",
                }
            }
        SQLiteEvaluationRepository(db_path).insert(
            Evaluation(
                article_id=article.id,
                evaluator="llm_relevance" if with_ai_payloads else "rule_relevance",
                evaluator_version="0.1.0",
                kind="relevance",
                score=85,
                confidence=0.9,
                rationale="Matched include terms ['statistics'].",
                payload=payload,
            )
        )

    if with_proposal_publication:
        proposal = IssueProposal(
            optimiser="greedy",
            article_ids=[article.id],
            objective_value=72.5,
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

    return article


def test_article_inspection_service_builds_editorial_context(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path, with_proposal_publication=True)

    inspection = _service(db_path).get(article.id)

    assert inspection is not None
    assert inspection.article == article
    assert inspection.extractions[0].extraction.kind == "reading_time"
    assert inspection.evaluations[0].evaluation.kind == "relevance"
    assert inspection.proposals[0].article_ids == [article.id]
    assert inspection.publications[0].title == "BIS Newsletter"


def test_cli_article_list_discovers_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path)

    result = CliRunner().invoke(app, ["article", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Articles" in result.stdout
    assert str(article.id) in result.stdout
    assert "Industrial statistics" in result.stdout


def test_cli_article_list_displays_extraction_and_evaluation_counts(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_article(db_path)

    result = CliRunner().invoke(app, ["article", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Extractions: 1" in result.stdout
    assert "Evaluations: 1" in result.stdout


def test_cli_article_show_displays_identity_fields(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "https://example.org/industrial-statistics" in result.stdout
    assert "new" in result.stdout


def test_cli_article_show_displays_summary_and_content_preview(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "A short summary about industrial statistics." in result.stdout
    assert "Industrial statistics content." in result.stdout
    assert len(result.stdout) < len(article.content or "") + 5000


def test_cli_article_show_displays_related_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Extractions" in result.stdout
    assert "reading_time" in result.stdout
    assert "Reading minutes" in result.stdout
    assert "Word count" in result.stdout


def test_cli_article_show_displays_related_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Evaluations" in result.stdout
    assert "rule_relevance" in result.stdout
    assert "85" in result.stdout
    assert "Matched include terms" in result.stdout


def test_cli_article_show_displays_ai_provenance_for_related_outputs(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path, with_ai_payloads=True)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "AI provenance" in result.stdout
    assert "fake-summary-model" in result.stdout
    assert "fake-relevance-model" in result.stdout
    assert "summary-v1" in result.stdout
    assert "relevance-v1" in result.stdout


def test_cli_article_show_handles_missing_optional_related_artefacts(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path, with_extraction=False, with_evaluation=False)

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No extractions found." in result.stdout
    assert "No evaluations found." in result.stdout
    assert "No proposals found." in result.stdout
    assert "No publications found." in result.stdout


def test_cli_article_show_displays_proposals_publications_and_workflow(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = _store_article(db_path, with_proposal_publication=True)
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="article",
            artefact_id=article.id,
            event_type="article-reviewed",
            actor="Andy",
            reason="Looks relevant",
        )
    )

    result = CliRunner().invoke(
        app, ["article", "show", str(article.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Proposals" in result.stdout
    assert "Publications" in result.stdout
    assert "BIS Newsletter" in result.stdout
    assert "article-reviewed" in result.stdout
    assert "Looks relevant" in result.stdout


def test_cli_article_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_id = uuid4()

    result = CliRunner().invoke(
        app, ["article", "show", str(article_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Article not found: {article_id}" in result.stdout
