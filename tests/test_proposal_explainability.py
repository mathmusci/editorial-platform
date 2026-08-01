from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.explain import ProposalExplanationService
from editorial.inspection import ProposalInspectionService
from editorial.models import (
    Article,
    ConstraintResult,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
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


def _inspection_service(db_path) -> ProposalInspectionService:
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


def _explanation_service(db_path) -> ProposalExplanationService:
    return ProposalExplanationService(_inspection_service(db_path))


def _store_explainable_proposal(
    db_path,
    *,
    with_extraction: bool = True,
    with_evaluation: bool = True,
    with_constraints: bool = True,
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
    )
    constraints = []
    if with_constraints:
        constraints = [
            ConstraintResult(
                name="max_articles",
                kind="hard",
                satisfied=True,
                value=1,
                target=2,
                penalty=0,
                message="Within article limit",
            ),
            ConstraintResult(
                name="relevance_target_score",
                kind="soft",
                satisfied=False,
                value=35,
                target=40,
                penalty=33,
                message="Below relevance target",
            ),
            ConstraintResult(
                name="reading_time_target_minutes",
                kind="soft",
                satisfied=False,
                value=4,
                target=20,
                penalty=10,
                message="Below reading-time target",
            ),
        ]
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id],
        objective_value=-43 if with_constraints else 12,
        constraint_results=constraints,
        metadata={"optimisation_request_id": str(request.id)},
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


def test_explanation_service_builds_explanation_from_proposal_inspection(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, _article = _store_explainable_proposal(db_path)
    inspection = _inspection_service(db_path).get(proposal.id)

    explanation = _explanation_service(db_path).build(inspection)

    assert explanation.proposal_id == proposal.id
    assert explanation.optimisation_request_id == request.id
    assert explanation.publication_name == "BIS Newsletter"
    assert explanation.selected_article_count == 1
    assert explanation.trade_off_summary.total_reading_minutes == 4
    assert explanation.trade_off_summary.average_relevance_score == 85


def test_cli_explain_proposal_works(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Proposal Identity" in result.stdout
    assert "Summary" in result.stdout


def test_cli_explain_includes_proposal_and_request_ids(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(proposal.id) in result.stdout
    assert str(request.id) in result.stdout


def test_cli_explain_includes_deterministic_editorial_summary(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "This proposal selected 1 article for BIS Newsletter" in result.stdout
    assert "greedy optimiser" in result.stdout
    assert "satisfies 1 of 3 recorded constraints" in result.stdout


def test_cli_explain_includes_constraint_explanations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Why It Happened" in result.stdout
    assert "Constraints and Trade-offs" in result.stdout
    assert "max_articles was satisfied" in result.stdout
    assert "relevance_target_score was not satisfied" in result.stdout


def test_explanation_orders_penalty_breakdown_by_penalty_descending(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    explanation = _explanation_service(db_path).get(proposal.id)

    assert explanation is not None
    assert [
        constraint.name
        for constraint in explanation.penalty_breakdown.ordered_constraints
    ] == [
        "relevance_target_score",
        "reading_time_target_minutes",
        "max_articles",
    ]


def test_cli_explain_includes_selected_article_titles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout


def test_cli_explain_includes_reading_time_and_relevance(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(db_path)

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Reading time:" in result.stdout
    assert "4" in result.stdout
    assert "Relevance score:" in result.stdout
    assert "85" in result.stdout
    assert "Matched include terms" in result.stdout


def test_cli_explain_handles_missing_extraction_and_evaluation_data(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(
        db_path, with_extraction=False, with_evaluation=False
    )

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Included in the stored proposal" in result.stdout
    assert "no evaluation details are available" in result.stdout
    assert "1 missing relevance evaluation" in result.stdout
    assert "missing reading-time extraction" in result.stdout


def test_cli_explain_handles_proposal_with_no_constraint_results(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _article = _store_explainable_proposal(
        db_path, with_constraints=False
    )

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No constraint results were recorded." in result.stdout
    assert "satisfies 0 of 0 recorded constraints" in result.stdout


def test_cli_explain_invalid_proposal_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal_id = uuid4()

    result = CliRunner().invoke(
        app, ["explain", "proposal", str(proposal_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Issue proposal not found: {proposal_id}" in result.stdout
