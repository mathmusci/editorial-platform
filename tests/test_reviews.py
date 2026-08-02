import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from editorial.cli import app
from editorial.models import IssueProposal, Review, ReviewDecision
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


def test_review_model_validation_and_immutability():
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=uuid4(),
        reviewer="Andy",
        decision=ReviewDecision.NEEDS_CHANGES,
        comments="Reading time too long",
        findings={"reading_time": 24},
        recommendations={"target_minutes": 20},
    )

    assert review.decision == ReviewDecision.NEEDS_CHANGES
    assert review.findings == {"reading_time": 24}

    with pytest.raises(ValidationError):
        Review(
            artefact_type="",
            artefact_id=uuid4(),
            reviewer="Andy",
            decision=ReviewDecision.COMMENT,
        )

    with pytest.raises(ValidationError):
        review.decision = ReviewDecision.APPROVE  # type: ignore[misc]


def test_review_repository_insert_list_get_count_and_json_persistence(tmp_path):
    repo = SQLiteReviewRepository(tmp_path / "test.sqlite")
    artefact_id = uuid4()
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=artefact_id,
        reviewer="Andy",
        decision=ReviewDecision.NEEDS_CHANGES,
        comments="Reading time too long",
        findings={"reading_time": {"actual": 24, "target": 20}},
        recommendations={"remove_article": "example"},
        metadata={"source": "manual"},
    )

    repo.insert(review)

    assert repo.count() == 1
    assert repo.get(review.id) == review
    assert repo.list(artefact_type="issue_proposal", artefact_id=artefact_id) == [
        review
    ]
    assert repo.list(artefact_type="publication") == []


def test_review_repository_is_append_only(tmp_path):
    repo = SQLiteReviewRepository(tmp_path / "test.sqlite")
    artefact_id = uuid4()

    repo.insert(
        Review(
            artefact_type="evaluation",
            artefact_id=artefact_id,
            reviewer="Andy",
            decision=ReviewDecision.COMMENT,
        )
    )
    repo.insert(
        Review(
            artefact_type="evaluation",
            artefact_id=artefact_id,
            reviewer="Blair",
            decision=ReviewDecision.APPROVE,
        )
    )

    assert repo.count() == 2


def test_review_repository_only_persists_review(tmp_path):
    db_path = tmp_path / "test.sqlite"
    artefact_id = uuid4()
    review = Review(
        artefact_type="extraction",
        artefact_id=artefact_id,
        reviewer="Andy",
        decision=ReviewDecision.REJECT,
    )

    SQLiteReviewRepository(db_path).insert(review)

    assert SQLiteReviewRepository(db_path).count() == 1
    assert SQLiteWorkflowEventRepository(db_path).count() == 0


@pytest.mark.parametrize(
    "artefact_type",
    ["issue_proposal", "publication", "evaluation"],
)
def test_reviews_attach_to_generic_artefact_types(tmp_path, artefact_type):
    repo = SQLiteReviewRepository(tmp_path / "test.sqlite")
    artefact_id = uuid4()
    review = Review(
        artefact_type=artefact_type,
        artefact_id=artefact_id,
        reviewer="Andy",
        decision=ReviewDecision.COMMENT,
    )

    repo.insert(review)

    assert repo.list(artefact_type=artefact_type) == [review]


def test_reviews_do_not_modify_proposals_or_create_optimisation_requests(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal_repo = SQLiteIssueProposalRepository(db_path)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[uuid4()],
        objective_value=10,
        metadata={"optimisation_request_id": str(uuid4())},
    )
    proposal_repo.insert(proposal)

    SQLiteReviewRepository(db_path).insert(
        Review(
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            reviewer="Andy",
            decision=ReviewDecision.NEEDS_CHANGES,
            recommendations={"rerun": True},
        )
    )

    assert proposal_repo.get(proposal.id) == proposal
    assert SQLiteIssueProposalRepository(db_path).count() == 1
    assert SQLiteOptimisationRequestRepository(db_path).count() == 0


def test_review_insert_duplicate_id_is_rejected(tmp_path):
    repo = SQLiteReviewRepository(tmp_path / "test.sqlite")
    review = Review(
        artefact_type="publication",
        artefact_id=uuid4(),
        reviewer="Andy",
        decision=ReviewDecision.APPROVE,
    )

    repo.insert(review)

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(review)


def test_cli_review_create_list_show_and_workflow_history(tmp_path):
    db_path = tmp_path / "test.sqlite"
    artefact_id = uuid4()
    runner = CliRunner()

    create = runner.invoke(
        app,
        [
            "review",
            "create",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(artefact_id),
            "--reviewer",
            "Andy",
            "--decision",
            "needs_changes",
            "--comments",
            "Reading time too long",
            "--finding",
            "reading_time=24",
            "--recommendation",
            "target_minutes=20",
            "--db",
            str(db_path),
        ],
    )
    review_id = create.stdout.strip().split()[-1]
    list_result = runner.invoke(
        app,
        [
            "review",
            "list",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(artefact_id),
            "--db",
            str(db_path),
        ],
    )
    show = runner.invoke(app, ["review", "show", review_id, "--db", str(db_path)])
    history = runner.invoke(
        app,
        [
            "workflow",
            "history",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(artefact_id),
            "--db",
            str(db_path),
        ],
    )

    assert create.exit_code == 0
    assert "Created review" in create.stdout
    assert SQLiteReviewRepository(db_path).count() == 1
    assert list_result.exit_code == 0
    assert review_id in list_result.stdout
    assert show.exit_code == 0
    assert "Decision: needs_changes" in show.stdout
    assert "Reading time" in show.stdout
    assert "24" in show.stdout
    assert "Target minutes" in show.stdout
    assert "20" in show.stdout
    assert history.exit_code == 0
    assert "review-submitted" in history.stdout
    events = SQLiteWorkflowEventRepository(db_path).list(
        artefact_type="issue_proposal", artefact_id=artefact_id
    )
    assert events[0].actor == "Andy"
    assert events[0].payload == {
        "review_id": review_id,
        "decision": "needs_changes",
    }
