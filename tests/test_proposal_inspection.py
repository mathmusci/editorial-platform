from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import ProposalInspectionService
from editorial.models import (
    Article,
    ConstraintResult,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
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
from editorial.web import create_app


def _service(db_path) -> ProposalInspectionService:
    return ProposalInspectionService(
        proposals=SQLiteIssueProposalRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        evaluations=SQLiteEvaluationRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
        reviews=SQLiteReviewRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
    )


def _store_proposal(
    db_path,
    *,
    with_extraction: bool = True,
    with_evaluation: bool = True,
    metadata: dict | None = None,
) -> tuple[IssueProposal, OptimisationRequest, Article]:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
        summary="Useful statistics.",
    )
    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 1},
        created_by="Tester",
    )
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id],
        objective_value=72.5,
        constraint_results=[
            ConstraintResult(
                name="reading_time",
                kind="soft",
                satisfied=True,
                value=4,
                target=20,
                penalty=0,
                message="Within target",
            )
        ],
        metadata={
            "optimisation_request_id": str(request.id),
            **(metadata or {}),
        },
    )

    SQLiteArticleRepository(db_path).upsert(article)
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    SQLiteIssueProposalRepository(db_path).insert(proposal)
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
                rationale="Matched include terms ['statistics'].",
            )
        )
    return proposal, request, article


def test_proposal_inspection_service_builds_review_model(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, _article = _store_proposal(db_path)

    inspection = _service(db_path).get(proposal.id)

    assert inspection is not None
    assert inspection.proposal.id == proposal.id
    assert inspection.optimisation_request == request
    assert inspection.publication_name == "BIS Newsletter"
    assert inspection.selected_articles[0].title == "Industrial statistics"
    assert inspection.selected_articles[0].reading_minutes == 4
    assert inspection.selected_articles[0].relevance_score == 85


def test_cli_proposal_list_discovers_proposals(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, _article = _store_proposal(db_path)

    result = CliRunner().invoke(app, ["proposal", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Issue Proposals" in result.stdout
    assert str(proposal.id) in result.stdout
    assert str(request.id) in result.stdout
    assert "BIS Newsletter" in result.stdout


def test_cli_proposal_show_displays_selected_article_titles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_proposal(db_path)

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "https://example.org/industrial-statistics" in result.stdout
    assert "4 min" in result.stdout
    assert "85" in result.stdout


def test_cli_proposal_show_displays_optimisation_request_linkage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, _article = _store_proposal(db_path)

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Optimisation request:" in result.stdout
    assert str(request.id) in result.stdout


def test_cli_proposal_show_filters_structurally_rendered_metadata(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_proposal(
        db_path,
        metadata={
            "candidate_count": 3,
            "selected_article_ids": ["already-rendered"],
        },
    )

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Candidate count" in result.stdout
    assert "3" in result.stdout
    assert "selected_article_ids" not in result.stdout
    assert '{"candidate_count"' not in result.stdout


def test_cli_proposal_show_handles_missing_optional_extraction_and_evaluation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_proposal(
        db_path, with_extraction=False, with_evaluation=False
    )

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Industrial statistics" in result.stdout
    assert "not available" in result.stdout


@pytest.mark.parametrize("strategy", ["greedy", "milp"])
def test_proposal_objective_breakdown_uses_saved_evidence(tmp_path, strategy):
    db_path = tmp_path / "test.sqlite"
    articles = [
        Article(title="Statistics", source="A"),
        Article(title="Industry", source="A"),
    ]
    for article in articles:
        SQLiteArticleRepository(db_path).insert(article)
    request = OptimisationRequest(
        strategy=strategy,
        settings={
            "relevance_target_score": 40,
            "reading_time_target_minutes": 12,
            "mandatory_terms": ["statistics", "industry"],
            "source_diversity_max_per_source": 1,
        },
    )
    proposal = IssueProposal(
        optimiser=strategy,
        article_ids=[article.id for article in articles],
        objective_value=28,
        metadata={
            "optimisation_request_id": str(request.id),
            "selected": [
                {
                    "article_id": str(article.id),
                    "relevance_score": score,
                    "reading_minutes": minutes,
                    "mandatory_terms": [term],
                    "source": "A",
                }
                for article, score, minutes, term in zip(
                    articles, (30, 20), (5, 7), ("statistics", "industry")
                )
            ],
        },
    )
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    SQLiteIssueProposalRepository(db_path).insert(proposal)

    inspection = _service(db_path).get(proposal.id)

    assert inspection is not None
    breakdown = inspection.objective_breakdown
    assert breakdown is not None
    assert breakdown.relevance_total == 50
    assert breakdown.mandatory_terms_reward == 10
    assert breakdown.relevance_target_penalty == 30
    assert breakdown.reading_minutes_total == 12
    assert breakdown.reading_time_penalty == 0
    assert breakdown.source_diversity_penalty == 2

    cli = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )
    assert cli.exit_code == 0
    assert "Objective Breakdown" in cli.stdout
    assert "+50.00" in cli.stdout
    assert "-30.00" in cli.stdout
    assert "-2.00" in cli.stdout
    assert "-0.00" not in cli.stdout

    with TestClient(
        create_app("tests/fixtures/bis/publication.yaml", db_path)
    ) as client:
        page = client.get(f"/proposals/{proposal.id}")
    assert page.status_code == 200
    assert "Objective breakdown" in page.text
    assert "Relevance scores, summed" in page.text
    assert "-30.00" in page.text


def test_proposal_objective_breakdown_is_unavailable_without_saved_snapshot(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_proposal(db_path)

    inspection = _service(db_path).get(proposal.id)

    assert inspection is not None
    assert inspection.objective_breakdown is None
    with TestClient(
        create_app("tests/fixtures/bis/publication.yaml", db_path)
    ) as client:
        page = client.get(f"/proposals/{proposal.id}")
    assert "Breakdown unavailable" in page.text


def test_cli_proposal_show_includes_workflow_review_and_publication_references(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_proposal(db_path)
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=proposal.id,
        reviewer="Andy",
        decision=ReviewDecision.APPROVE,
        comments="Looks good",
    )
    publication = Publication(proposal_id=proposal.id, title="BIS Newsletter")
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            event_type="proposal-created",
            actor="optimiser",
        )
    )
    SQLiteReviewRepository(db_path).insert(review)
    SQLitePublicationRepository(db_path).insert(publication)

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "proposal-created" in result.stdout
    assert str(review.id) in result.stdout
    assert "approve" in result.stdout
    assert str(publication.id) in result.stdout
    assert "BIS Newsletter" in result.stdout


def test_cli_proposal_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal_id = uuid4()

    result = CliRunner().invoke(
        app, ["proposal", "show", str(proposal_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Issue proposal not found: {proposal_id}" in result.stdout
