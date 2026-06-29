from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from editorial.cli import app
from editorial.engine import EditorialEngine
from editorial.models import Article, Evaluation, OptimisationRequest
from editorial.optimisers import GreedyOptimiser
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteWorkflowEventRepository,
)
from editorial.workflow import WorkflowProjection


def test_optimisation_request_model_validation_and_immutability():
    request = OptimisationRequest(
        publication="BIS",
        strategy="greedy",
        settings={"max_articles": 1},
        constraints={"minimum_relevance": 40},
        goals={"maximise": ["relevance"]},
        preferences={"tone": "concise"},
        created_by="Andy",
    )

    assert request.strategy == "greedy"
    assert request.settings == {"max_articles": 1}

    with pytest.raises(ValidationError):
        OptimisationRequest(strategy="")

    with pytest.raises(ValidationError):
        request.strategy = "other"  # type: ignore[misc]


def test_optimisation_request_repository_insert_list_get_and_count(tmp_path):
    repo = SQLiteOptimisationRequestRepository(tmp_path / "test.sqlite")
    request = OptimisationRequest(
        publication="BIS",
        strategy="greedy",
        settings={"max_articles": 3},
        created_by="Andy",
    )

    repo.insert(request)

    assert repo.count() == 1
    assert repo.list() == [request]
    assert repo.get(request.id) == request


def test_optimisation_request_repository_is_append_only(tmp_path):
    repo = SQLiteOptimisationRequestRepository(tmp_path / "test.sqlite")

    repo.insert(OptimisationRequest(strategy="greedy"))
    repo.insert(OptimisationRequest(strategy="greedy"))

    assert repo.count() == 2


def test_engine_runs_optimisation_request_and_records_workflow_event(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    proposal_repo = SQLiteIssueProposalRepository(db_path)
    workflow_repo = SQLiteWorkflowEventRepository(db_path)
    article = Article(title="Industrial statistics", url="https://example.org/a")
    article_repo.upsert(article)
    evaluation_repo.insert(
        Evaluation(
            article_id=article.id,
            evaluator="rule_relevance",
            kind="relevance",
            score=75,
        )
    )
    request = OptimisationRequest(
        publication="BIS",
        strategy="greedy",
        settings={"max_articles": 1, "relevance_target_score": 40},
        created_by="Andy",
    )
    engine = EditorialEngine(
        article_repo,
        extraction_repo,
        evaluation_repo,
        proposal_repo,
        workflow_repo,
    )

    result = engine.optimise_request(GreedyOptimiser(), request)

    proposal = proposal_repo.get(result.proposal_id)
    events = workflow_repo.list(
        artefact_type="issue_proposal", artefact_id=proposal.id if proposal else None
    )
    assert proposal is not None
    assert proposal.metadata["optimisation_request_id"] == str(request.id)
    assert proposal_repo.count() == 1
    assert len(events) == 1
    assert events[0].event_type == "proposal-created"
    assert events[0].actor == "Andy"
    assert events[0].payload["optimisation_request_id"] == str(request.id)
    assert WorkflowProjection().state_for(events) == "draft"


def test_cli_optimisation_request_create_list_show_and_run(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    for command in ["ingest", "extract", "evaluate"]:
        result = runner.invoke(
            app,
            [
                command,
                "--config",
                "examples/bis/publication.yaml",
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

    create = runner.invoke(
        app,
        [
            "optimisation-request",
            "create",
            "--config",
            "examples/bis/publication.yaml",
            "--created-by",
            "Andy",
            "--db",
            str(db_path),
        ],
    )
    request_id = create.stdout.strip().split()[-1]
    list_result = runner.invoke(
        app, ["optimisation-request", "list", "--db", str(db_path)]
    )
    show = runner.invoke(
        app, ["optimisation-request", "show", request_id, "--db", str(db_path)]
    )
    run = runner.invoke(
        app, ["optimisation-request", "run", request_id, "--db", str(db_path)]
    )

    assert create.exit_code == 0
    assert "Created optimisation request" in create.stdout
    assert SQLiteOptimisationRequestRepository(db_path).count() == 1
    assert list_result.exit_code == 0
    assert request_id in list_result.stdout
    assert show.exit_code == 0
    assert "Strategy: greedy" in show.stdout
    assert run.exit_code == 0
    assert "Created issue proposal" in run.stdout
    assert SQLiteIssueProposalRepository(db_path).count() == 1
    assert SQLiteWorkflowEventRepository(db_path).count() == 1


def test_existing_optimise_command_creates_request_and_workflow_event(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    for command in ["ingest", "extract", "evaluate"]:
        result = runner.invoke(
            app,
            [
                command,
                "--config",
                "examples/bis/publication.yaml",
                "--db",
                str(db_path),
            ],
        )
        assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["optimise", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Optimisation request:" in result.stdout
    proposal = SQLiteIssueProposalRepository(db_path).list()[0]
    assert "optimisation_request_id" in proposal.metadata
    assert SQLiteOptimisationRequestRepository(db_path).count() == 1
    assert SQLiteWorkflowEventRepository(db_path).count() == 1


def test_cli_optimisation_request_accepts_parent_ids(tmp_path):
    db_path = tmp_path / "test.sqlite"
    parent_request_id = uuid4()
    parent_proposal_id = uuid4()
    result = CliRunner().invoke(
        app,
        [
            "optimisation-request",
            "create",
            "--config",
            "examples/bis/publication.yaml",
            "--parent-request-id",
            str(parent_request_id),
            "--parent-proposal-id",
            str(parent_proposal_id),
            "--db",
            str(db_path),
        ],
    )

    request = SQLiteOptimisationRequestRepository(db_path).list()[0]
    assert result.exit_code == 0
    assert request.parent_request_id == parent_request_id
    assert request.parent_proposal_id == parent_proposal_id
