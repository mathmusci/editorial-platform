from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import PublicationInspectionService
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
    PublicationSection,
    Review,
    ReviewDecision,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> PublicationInspectionService:
    return PublicationInspectionService(
        publications=SQLitePublicationRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        evaluations=SQLiteEvaluationRepository(db_path),
        reviews=SQLiteReviewRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_publication(
    db_path,
    *,
    with_proposal: bool = True,
    with_extraction: bool = True,
    with_evaluation: bool = True,
    with_review: bool = False,
    with_workflow: bool = False,
) -> tuple[Publication, Article, IssueProposal | None, OptimisationRequest | None]:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
        summary="A concise article summary.",
    )
    SQLiteArticleRepository(db_path).upsert(article)

    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 1},
    )
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id],
        objective_value=72.5,
        metadata={"optimisation_request_id": str(request.id)},
    )
    if with_proposal:
        SQLiteOptimisationRequestRepository(db_path).insert(request)
        SQLiteIssueProposalRepository(db_path).insert(proposal)
    else:
        request = None
        proposal = None

    proposal_id = proposal.id if proposal else uuid4()
    publication = Publication(
        proposal_id=proposal_id,
        title="BIS Newsletter",
        subtitle="Draft issue",
        sections=[
            PublicationSection(
                heading="Selected articles",
                article_ids=[article.id],
                summary="This section contains one article.",
            )
        ],
        metadata={"article_count": 1},
    )
    SQLitePublicationRepository(db_path).insert(publication)

    if with_extraction:
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="reading_time",
                kind="reading_time",
                payload={"reading_minutes": 4, "word_count": 700},
            )
        )

    if with_evaluation:
        SQLiteEvaluationRepository(db_path).insert(
            Evaluation(
                article_id=article.id,
                evaluator="rule_relevance",
                kind="relevance",
                score=85,
                confidence=0.9,
                rationale="Matched include terms ['statistics'].",
            )
        )

    if with_review:
        SQLiteReviewRepository(db_path).insert(
            Review(
                artefact_type="issue_proposal",
                artefact_id=publication.proposal_id,
                reviewer="Andy",
                decision=ReviewDecision.APPROVE,
                comments="Ready to publish",
            )
        )

    if with_workflow:
        workflow_repo = SQLiteWorkflowEventRepository(db_path)
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-created",
                actor="CLI",
            )
        )
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-published",
                actor="CLI",
                payload={"format": "markdown", "output_path": "newsletter.md"},
            )
        )
        if proposal is not None:
            workflow_repo.insert(
                WorkflowEvent(
                    artefact_type="issue_proposal",
                    artefact_id=proposal.id,
                    event_type="proposal-created",
                    actor="optimiser",
                )
            )

    return publication, article, proposal, request


def test_publication_inspection_service_builds_review_model(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, article, proposal, request = _store_publication(
        db_path, with_review=True, with_workflow=True
    )

    inspection = _service(db_path).get(publication.id)

    assert inspection is not None
    assert inspection.publication == publication
    assert inspection.proposal == proposal
    assert inspection.optimisation_request == request
    assert inspection.sections[0].articles[0].article == article
    assert inspection.sections[0].articles[0].reading_minutes == 4
    assert inspection.sections[0].articles[0].relevance_score == 85
    assert len(inspection.proposal_reviews) == 1
    assert len(inspection.rendered_outputs) == 1


def test_cli_publication_list_discovers_publications(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(app, ["publication", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Publications" in result.stdout
    assert str(publication.id) in result.stdout
    assert "BIS Newsletter" in result.stdout


def test_cli_publication_list_displays_title_proposal_sections_and_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(app, ["publication", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "BIS Newsletter" in result.stdout
    assert str(publication.proposal_id) in result.stdout
    assert "Sections: 1" in result.stdout
    assert "Articles: 1" in result.stdout


def test_cli_publication_show_displays_title_subtitle_and_proposal_linkage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, proposal, request = _store_publication(db_path)

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "BIS Newsletter" in result.stdout
    assert "Draft issue" in result.stdout
    assert str(proposal.id) in result.stdout
    assert str(request.id) in result.stdout


def test_cli_publication_show_displays_sections_and_included_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Section 1: Selected articles" in result.stdout
    assert "Industrial statistics" in result.stdout


def test_cli_publication_show_displays_article_source_and_url(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Fixture Source" in result.stdout
    assert "https://example.org/industrial-statistics" in result.stdout


def test_cli_publication_show_displays_related_reading_time_extraction(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Reading time: 4" in result.stdout


def test_cli_publication_show_displays_related_relevance_evaluation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(db_path)

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Relevance: 85" in result.stdout
    assert "Matched include terms" in result.stdout


def test_cli_publication_show_displays_proposal_reviews(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(
        db_path, with_review=True
    )

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Proposal Reviews" in result.stdout
    assert "Andy" in result.stdout
    assert "approve" in result.stdout
    assert "Ready to publish" in result.stdout


def test_cli_publication_show_handles_missing_proposal_gracefully(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(
        db_path, with_proposal=False
    )

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(publication.proposal_id) in result.stdout
    assert "Optimisation request: not available" in result.stdout
    assert "No proposal workflow events found." in result.stdout


def test_cli_publication_show_handles_missing_extraction_and_evaluation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(
        db_path, with_extraction=False, with_evaluation=False
    )

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Reading time: not available" in result.stdout
    assert "Relevance: not available" in result.stdout


def test_cli_publication_show_displays_publication_workflow_and_rendered_outputs(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"
    publication, _article, _proposal, _request = _store_publication(
        db_path, with_workflow=True
    )

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Publication Workflow" in result.stdout
    assert "publication-created" in result.stdout
    assert "publication-published" in result.stdout
    assert "Rendered Outputs" in result.stdout
    assert "markdown" in result.stdout
    assert "newsletter.md" in result.stdout


def test_cli_publication_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication_id = uuid4()

    result = CliRunner().invoke(
        app, ["publication", "show", str(publication_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Publication not found: {publication_id}" in result.stdout
