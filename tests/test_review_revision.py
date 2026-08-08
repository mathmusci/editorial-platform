import re
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.models import (
    IssueProposal,
    OptimisationRequest,
    Review,
    ReviewDecision,
)
from editorial.revisions import ReviewRevisionService
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)
from editorial.workflow import WorkflowProjection

BIS_FIXTURE_CONFIG = "tests/fixtures/bis/publication.yaml"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _unstyled(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _service(db_path) -> ReviewRevisionService:
    return ReviewRevisionService(
        reviews=SQLiteReviewRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_revision_fixture(
    db_path,
    *,
    decision: ReviewDecision = ReviewDecision.NEEDS_CHANGES,
    artefact_type: str = "issue_proposal",
    with_proposal: bool = True,
    with_request_link: bool = True,
) -> tuple[Review, IssueProposal, OptimisationRequest]:
    source_request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 6, "reading_time_target_minutes": 20},
        created_by="Original editor",
    )
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[uuid4()],
        objective_value=75,
        metadata=(
            {"optimisation_request_id": str(source_request.id)}
            if with_request_link
            else {}
        ),
    )
    if with_proposal:
        SQLiteOptimisationRequestRepository(db_path).insert(source_request)
        SQLiteIssueProposalRepository(db_path).insert(proposal)
    review = Review(
        artefact_type=artefact_type,
        artefact_id=proposal.id,
        reviewer="Andy",
        decision=decision,
        comments="Reduce the total reading time.",
        findings={"reading_time": {"actual": 24, "target": 18}},
        recommendations={"reading_time_target_minutes": 18},
    )
    SQLiteReviewRepository(db_path).insert(review)
    return review, proposal, source_request


def test_service_creates_immutable_revision_request_with_review_lineage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, source_request = _store_revision_fixture(db_path)
    template = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 6, "reading_time_target_minutes": 20},
        constraints={"required": True},
        goals={"maximise": ["relevance"]},
        preferences={"tone": "concise"},
        metadata={"config": "candidate.yaml"},
    )

    revision = _service(db_path).create(
        review.id,
        template,
        created_by="Revision editor",
        settings={"reading_time_target_minutes": 18},
        constraints={"required": False},
        preferences={"audience": "executives"},
    )

    request = revision.request
    assert revision.source_proposal_id == proposal.id
    assert revision.source_request_id == source_request.id
    assert request.parent_request_id == source_request.id
    assert request.parent_proposal_id == proposal.id
    assert request.created_by == "Revision editor"
    assert request.settings == {
        "max_articles": 6,
        "reading_time_target_minutes": 18,
    }
    assert request.constraints == {"required": False}
    assert request.goals == {"maximise": ["relevance"]}
    assert request.preferences == {"tone": "concise", "audience": "executives"}
    assert request.metadata["source_review_id"] == str(review.id)
    assert request.metadata["review_findings"] == review.findings
    assert request.metadata["review_recommendations"] == review.recommendations
    assert SQLiteOptimisationRequestRepository(db_path).count() == 2
    assert SQLiteIssueProposalRepository(db_path).get(proposal.id) == proposal
    assert SQLiteReviewRepository(db_path).get(review.id) == review


def test_service_records_revision_workflow_on_all_lineage_artefacts(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, _source_request = _store_revision_fixture(db_path)

    revision = _service(db_path).create(
        review.id,
        OptimisationRequest(publication="BIS Newsletter", strategy="greedy"),
    )

    events = SQLiteWorkflowEventRepository(db_path)
    proposal_events = events.list(
        artefact_type="issue_proposal", artefact_id=proposal.id
    )
    review_events = events.list(artefact_type="review", artefact_id=review.id)
    request_events = events.list(
        artefact_type="optimisation_request", artefact_id=revision.request.id
    )
    assert [event.event_type for event in proposal_events] == ["revision-requested"]
    assert [event.event_type for event in review_events] == ["revision-request-created"]
    assert [event.event_type for event in request_events] == [
        "optimisation-request-created"
    ]
    assert proposal_events[0].actor == "Andy"
    assert proposal_events[0].payload["review_id"] == str(review.id)
    assert proposal_events[0].payload["revision_request_id"] == str(revision.request.id)
    assert WorkflowProjection().state_for(proposal_events) == "changes_requested"


@pytest.mark.parametrize(
    ("fixture_kwargs", "message"),
    [
        ({"decision": ReviewDecision.APPROVE}, "needs_changes"),
        ({"artefact_type": "publication"}, "issue_proposal review"),
        ({"with_proposal": False}, "Issue proposal not found"),
    ],
)
def test_service_rejects_reviews_that_cannot_create_a_revision(
    tmp_path, fixture_kwargs, message
):
    db_path = tmp_path / "test.sqlite"
    review, _proposal, _request = _store_revision_fixture(db_path, **fixture_kwargs)

    with pytest.raises(ValueError, match=message):
        _service(db_path).create(
            review.id,
            OptimisationRequest(publication="BIS Newsletter", strategy="greedy"),
        )


def test_service_allows_legacy_proposal_without_request_lineage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, _request = _store_revision_fixture(
        db_path, with_request_link=False
    )

    revision = _service(db_path).create(
        review.id,
        OptimisationRequest(publication="BIS Newsletter", strategy="greedy"),
    )

    assert revision.source_request_id is None
    assert revision.request.parent_request_id is None
    assert revision.request.parent_proposal_id == proposal.id


def test_cli_review_revise_creates_request_and_exposes_it_in_inspection(tmp_path):
    db_path = tmp_path / "test.sqlite"
    review, proposal, source_request = _store_revision_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "review",
            "revise",
            str(review.id),
            "--config",
            BIS_FIXTURE_CONFIG,
            "--created-by",
            "Revision editor",
            "--setting",
            "reading_time_target_minutes=18",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Created revision request" in result.stdout
    assert str(proposal.id) in result.stdout
    assert str(source_request.id) in result.stdout
    assert "Next: editorial optimisation-request run" in result.stdout
    requests = SQLiteOptimisationRequestRepository(db_path).list()
    revision_request = next(
        request for request in requests if request != source_request
    )
    assert revision_request.settings["reading_time_target_minutes"] == 18

    review_show = CliRunner().invoke(
        app, ["review", "show", str(review.id), "--db", str(db_path)]
    )
    request_show = CliRunner().invoke(
        app,
        [
            "optimisation-request",
            "show",
            str(revision_request.id),
            "--db",
            str(db_path),
        ],
    )
    review_output = _unstyled(review_show.stdout)
    request_output = _unstyled(request_show.stdout)
    assert review_show.exit_code == 0
    assert "Linked Revision Requests" in review_output
    assert str(revision_request.id) in review_output
    assert request_show.exit_code == 0
    assert f"Parent optimisation request: {source_request.id}" in request_output
    assert f"Parent proposal: {proposal.id}" in request_output
    assert str(review.id) in request_output


def test_cli_review_revise_can_run_and_suggest_proposal_comparison(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    for command in ("ingest", "extract", "evaluate"):
        result = runner.invoke(
            app,
            [command, "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
        )
        assert result.exit_code == 0

    create_request = runner.invoke(
        app,
        [
            "optimisation-request",
            "create",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--created-by",
            "Andy",
            "--db",
            str(db_path),
        ],
    )
    assert create_request.exit_code == 0
    source_request = SQLiteOptimisationRequestRepository(db_path).list()[0]
    run_request = runner.invoke(
        app,
        [
            "optimisation-request",
            "run",
            str(source_request.id),
            "--db",
            str(db_path),
        ],
    )
    assert run_request.exit_code == 0
    source_proposal = SQLiteIssueProposalRepository(db_path).list()[0]
    create_review = runner.invoke(
        app,
        [
            "review",
            "create",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(source_proposal.id),
            "--reviewer",
            "Andy",
            "--decision",
            "needs_changes",
            "--comments",
            "Use a shorter issue.",
            "--recommendation",
            "max_articles=1",
            "--db",
            str(db_path),
        ],
    )
    assert create_review.exit_code == 0
    review = SQLiteReviewRepository(db_path).list()[0]

    revision = runner.invoke(
        app,
        [
            "review",
            "revise",
            str(review.id),
            "--config",
            BIS_FIXTURE_CONFIG,
            "--setting",
            "max_articles=1",
            "--run",
            "--db",
            str(db_path),
        ],
    )

    output = " ".join(_unstyled(revision.output).replace("│", " ").split())
    assert revision.exit_code == 0
    assert "Created revised issue proposal" in output
    assert "Compare: editorial proposal compare" in output
    assert str(source_proposal.id) in output
    assert SQLiteIssueProposalRepository(db_path).count() == 2
    assert SQLiteOptimisationRequestRepository(db_path).count() == 2
