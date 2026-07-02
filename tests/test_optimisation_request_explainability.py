from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.explain import OptimisationRequestExplanationService
from editorial.models import ConstraintResult, IssueProposal, OptimisationRequest
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
)


def _service(db_path) -> OptimisationRequestExplanationService:
    return OptimisationRequestExplanationService(
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
    )


def _store_request_with_proposal(
    db_path,
    *,
    custom_setting: bool = False,
    linked_proposal: bool = True,
) -> tuple[OptimisationRequest, IssueProposal | None]:
    settings = {
        "max_articles": 2,
        "reading_time_target_minutes": 20,
        "reading_time_weight": 3,
        "relevance_target_score": 40,
        "mandatory_terms": ["statistics"],
        "source_diversity_max_per_source": 1,
    }
    if custom_setting:
        settings["experimental_knob"] = "on"
    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings=settings,
        constraints={"minimum_relevance": 40},
        goals={"maximise": ["relevance"]},
        preferences={"tone": "concise"},
        created_by="Andy",
    )
    SQLiteOptimisationRequestRepository(db_path).insert(request)

    proposal = None
    if linked_proposal:
        proposal = IssueProposal(
            optimiser="greedy",
            article_ids=[uuid4(), uuid4()],
            objective_value=-43,
            constraint_results=[
                ConstraintResult(
                    name="max_articles",
                    kind="hard",
                    satisfied=True,
                    value=2,
                    target=2,
                    penalty=0,
                ),
                ConstraintResult(
                    name="relevance_target_score",
                    kind="soft",
                    satisfied=False,
                    value=35,
                    target=40,
                    penalty=33,
                ),
                ConstraintResult(
                    name="reading_time_target_minutes",
                    kind="soft",
                    satisfied=False,
                    value=8,
                    target=20,
                    penalty=10,
                ),
            ],
            metadata={"optimisation_request_id": str(request.id)},
        )
        SQLiteIssueProposalRepository(db_path).insert(proposal)
    return request, proposal


def test_explanation_service_builds_explanation_for_optimisation_request(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, proposal = _store_request_with_proposal(db_path)

    explanation = _service(db_path).get(request.id)

    assert explanation is not None
    assert explanation.request_id == request.id
    assert explanation.publication == "BIS Newsletter"
    assert explanation.strategy == "greedy"
    assert explanation.linked_proposals[0].proposal_id == proposal.id
    assert explanation.linked_proposals[0].selected_article_count == 2


def test_cli_explain_optimisation_request_works(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Optimisation Request" in result.stdout
    assert "Editorial Summary" in result.stdout


def test_cli_output_includes_request_id_publication_and_strategy(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert str(request.id) in result.stdout
    assert "BIS Newsletter" in result.stdout
    assert "greedy" in result.stdout


def test_cli_output_includes_deterministic_editorial_summary(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "asked the greedy optimiser to construct a proposal" in result.stdout
    assert "1 proposal was produced" in result.stdout


def test_cli_output_includes_known_settings_explanations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "max_articles" in result.stdout
    assert "Maximum number of articles" in result.stdout
    assert "reading_time_target_minutes" in result.stdout
    assert "Target total reading time" in result.stdout


def test_cli_output_handles_unknown_custom_settings(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path, custom_setting=True)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "experimental_knob" in result.stdout
    assert "Custom setting recorded for this optimisation request." in result.stdout


def test_cli_output_links_proposals_by_optimisation_request_metadata(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert str(proposal.id) in result.stdout
    assert "Linked Proposals" in result.stdout


def test_cli_output_includes_selected_article_count_and_objective_value(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Selected articles: 2" in result.stdout
    assert "Objective value: -43.0" in result.stdout


def test_cli_output_includes_satisfied_and_failed_constraint_counts(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Satisfied constraints: 1" in result.stdout
    assert "Failed constraints: 2" in result.stdout


def test_explanation_orders_penalties_by_penalty_descending(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path)

    explanation = _service(db_path).get(request.id)

    assert explanation is not None
    assert explanation.linked_proposals[0].ordered_penalties == [
        ("relevance_target_score", 33.0),
        ("reading_time_target_minutes", 10.0),
        ("max_articles", 0.0),
    ]


def test_cli_output_handles_request_with_no_linked_proposal(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request, _proposal = _store_request_with_proposal(db_path, linked_proposal=False)

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request.id), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert (
        "No IssueProposal linked to this optimisation request was found."
        in result.stdout
    )
    assert "0 proposals were produced" in result.stdout


def test_cli_explain_invalid_optimisation_request_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    request_id = uuid4()

    result = CliRunner().invoke(
        app,
        ["explain", "optimisation-request", str(request_id), "--db", str(db_path)],
    )

    assert result.exit_code == 1
    assert f"Optimisation request not found: {request_id}" in result.stdout
