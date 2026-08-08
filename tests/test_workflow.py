from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from editorial.cli import app
from editorial.models import WorkflowEvent
from editorial.storage import SQLiteWorkflowEventRepository
from editorial.workflow import WorkflowProjection


def test_workflow_event_model_validation():
    event = WorkflowEvent(
        artefact_type="issue_proposal",
        artefact_id=uuid4(),
        event_type="review-requested",
        actor="Andy",
        reason="Ready for editorial review",
        payload={"priority": "normal"},
    )

    assert event.artefact_type == "issue_proposal"
    assert event.payload == {"priority": "normal"}

    with pytest.raises(ValidationError):
        WorkflowEvent(
            artefact_type="", artefact_id=uuid4(), event_type="review-requested"
        )

    with pytest.raises(ValidationError):
        WorkflowEvent(
            artefact_type="issue_proposal", artefact_id=uuid4(), event_type=""
        )


def test_workflow_event_repository_insert_list_get_and_count(tmp_path):
    repo = SQLiteWorkflowEventRepository(tmp_path / "test.sqlite")
    artefact_id = uuid4()
    event = WorkflowEvent(
        artefact_type="issue_proposal",
        artefact_id=artefact_id,
        event_type="proposal-created",
        payload={"source": "optimiser"},
    )

    repo.insert(event)

    assert repo.count() == 1
    listed = repo.list(artefact_type="issue_proposal", artefact_id=artefact_id)
    fetched = repo.get(event.id)
    assert listed == [event]
    assert fetched == event


def test_workflow_event_repository_filters_and_limits(tmp_path):
    repo = SQLiteWorkflowEventRepository(tmp_path / "test.sqlite")
    first_artefact_id = uuid4()
    second_artefact_id = uuid4()
    repo.insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=first_artefact_id,
            event_type="proposal-created",
        )
    )
    repo.insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=second_artefact_id,
            event_type="publication-created",
        )
    )

    assert len(repo.list(artefact_type="issue_proposal")) == 1
    assert len(repo.list(artefact_id=second_artefact_id)) == 1
    assert len(repo.list(limit=1)) == 1


def test_workflow_event_repository_is_append_only(tmp_path):
    repo = SQLiteWorkflowEventRepository(tmp_path / "test.sqlite")
    artefact_id = uuid4()

    repo.insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="review-requested",
        )
    )
    repo.insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="review-requested",
        )
    )

    assert repo.count() == 2


def test_workflow_projection_derives_state_from_history():
    artefact_id = uuid4()
    events = [
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="proposal-created",
        ),
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="review-requested",
        ),
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="review-submitted",
        ),
    ]

    assert WorkflowProjection().state_for(events) == "reviewed"


def test_workflow_projection_unknown_state_when_no_events_exist():
    assert WorkflowProjection().state_for([]) == "unknown"


def test_workflow_projection_marks_requested_revision_as_changes_requested():
    artefact_id = uuid4()
    events = [
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="proposal-created",
        ),
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="review-submitted",
        ),
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=artefact_id,
            event_type="revision-requested",
        ),
    ]

    assert WorkflowProjection().state_for(events) == "changes_requested"


def test_cli_workflow_record_history_and_state(tmp_path):
    db_path = tmp_path / "test.sqlite"
    artefact_id = uuid4()
    runner = CliRunner()

    record = runner.invoke(
        app,
        [
            "workflow",
            "record",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(artefact_id),
            "--event-type",
            "review-requested",
            "--actor",
            "Andy",
            "--reason",
            "Ready for editorial review",
            "--payload",
            '{"priority": "normal"}',
            "--db",
            str(db_path),
        ],
    )
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
    state = runner.invoke(
        app,
        [
            "workflow",
            "state",
            "--artefact-type",
            "issue_proposal",
            "--artefact-id",
            str(artefact_id),
            "--db",
            str(db_path),
        ],
    )

    assert record.exit_code == 0
    assert "Recorded workflow event" in record.stdout
    assert history.exit_code == 0
    assert "review-requested" in history.stdout
    assert state.exit_code == 0
    assert "Workflow state: under_review" in state.stdout
