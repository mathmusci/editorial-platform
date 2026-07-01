from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import ReviewInspectionService
from editorial.models import (
    IssueProposal,
    OptimisationRequest,
    Publication,
    Review,
    ReviewDecision,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> ReviewInspectionService:
    return ReviewInspectionService(
        reviews=SQLiteReviewRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_issue_proposal_review(
    db_path,
    *,
    with_proposal: bool = True,
    with_publication: bool = False,
    with_workflow: bool = False,
) -> tuple[
    Review, IssueProposal | None, OptimisationRequest | None, Publication | None
]:
    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 1},
    )
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[uuid4(), uuid4()],
        objective_value=72.5,
        metadata={"optimisation_request_id": str(request.id)},
    )
    if with_proposal:
        SQLiteOptimisationRequestRepository(db_path).insert(request)
        SQLiteIssueProposalRepository(db_path).insert(proposal)
    else:
        request = None
        proposal = None

    artefact_id = proposal.id if proposal else uuid4()
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=artefact_id,
        reviewer="Andy",
        decision=ReviewDecision.APPROVE,
        comments="Ready to publish",
        findings={"reading_time": 12},
        recommendations={"publish": True},
        metadata={"source": "manual"},
    )
    SQLiteReviewRepository(db_path).insert(review)

    publication = None
    if with_publication:
        publication = Publication(proposal_id=artefact_id, title="BIS Newsletter")
        SQLitePublicationRepository(db_path).insert(publication)

    if with_workflow:
        workflow_repo = SQLiteWorkflowEventRepository(db_path)
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="review",
                artefact_id=review.id,
                event_type="review-created",
                actor="Andy",
            )
        )
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="issue_proposal",
                artefact_id=artefact_id,
                event_type="review-submitted",
                actor="Andy",
                reason="Approved",
            )
        )

    return review, proposal, request, publication


def test_review_inspection_service_builds_issue_proposal_context(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, request, publication = _store_issue_proposal_review(
        db_path, with_publication=True, with_workflow=True
    )

    inspection = _service(db_path).get(review.id)

    assert inspection is not None
    assert inspection.review == review
    assert inspection.issue_proposal == proposal
    assert inspection.optimisation_request == request
    assert inspection.publications == [publication]
    assert inspection.detailed_inspection_available is True
    assert len(inspection.review_workflow_events) == 1
    assert len(inspection.artefact_workflow_events) == 1


def test_cli_review_list_discovers_reviews(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, _publication = _store_issue_proposal_review(db_path)

    result = CliRunner().invoke(app, ["review", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Reviews" in result.stdout
    assert str(review.id) in result.stdout


def test_cli_review_list_displays_reviewer_decision_and_artefact(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, _publication = _store_issue_proposal_review(db_path)

    result = CliRunner().invoke(app, ["review", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Andy" in result.stdout
    assert "approve" in result.stdout
    assert "issue_proposal" in result.stdout
    assert str(review.artefact_id) in result.stdout


def test_cli_review_show_displays_reviewer_decision_and_comments(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, _publication = _store_issue_proposal_review(db_path)

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Andy" in result.stdout
    assert "approve" in result.stdout
    assert "Ready to publish" in result.stdout


def test_cli_review_show_displays_reviewed_issue_proposal_context(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, _request, _publication = _store_issue_proposal_review(db_path)

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "IssueProposal Context" in result.stdout
    assert str(proposal.id) in result.stdout
    assert "Selected articles: 2" in result.stdout
    assert "Objective value: 72.5" in result.stdout


def test_cli_review_show_displays_originating_optimisation_request(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, request, _publication = _store_issue_proposal_review(db_path)

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(request.id) in result.stdout


def test_cli_review_show_displays_linked_publications(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, publication = _store_issue_proposal_review(
        db_path, with_publication=True
    )

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Linked Publications" in result.stdout
    assert str(publication.id) in result.stdout
    assert "BIS Newsletter" in result.stdout


def test_cli_review_show_handles_missing_reviewed_proposal_gracefully(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, _publication = _store_issue_proposal_review(
        db_path, with_proposal=False
    )

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(review.artefact_id) in result.stdout
    assert "IssueProposal not found." in result.stdout


def test_cli_review_show_handles_unsupported_reviewed_artefact_type(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review = Review(
        artefact_type="evaluation",
        artefact_id=uuid4(),
        reviewer="Blair",
        decision=ReviewDecision.COMMENT,
        comments="Looks plausible",
    )
    SQLiteReviewRepository(db_path).insert(review)

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "evaluation" in result.stdout
    assert (
        "Detailed inspection for this artefact type is not currently available."
        in result.stdout
    )


def test_cli_review_show_displays_review_workflow_events(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request, _publication = _store_issue_proposal_review(
        db_path, with_workflow=True
    )

    result = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Review Workflow" in result.stdout
    assert "review-created" in result.stdout
    assert "Artefact Workflow" in result.stdout
    assert "review-submitted" in result.stdout


def test_cli_review_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review_id = uuid4()

    result = CliRunner().invoke(
        app, ["review", "show", str(review_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Review not found: {review_id}" in result.stdout
