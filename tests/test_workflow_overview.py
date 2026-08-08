from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.evaluators import EvaluatorDescriptor
from editorial.extractors import ExtractorDescriptor
from editorial.inspection import WorkflowOverviewService
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
    PublicationArticle,
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

BIS_CONFIG = "tests/fixtures/bis/publication.yaml"
EXTRACTORS = [
    ExtractorDescriptor(
        key="reading_time", display_name="Reading time", kind="reading_time"
    )
]
EVALUATORS = [
    EvaluatorDescriptor(
        key="rule_relevance", display_name="BIS relevance", kind="relevance"
    )
]


def _service(db_path) -> WorkflowOverviewService:
    return WorkflowOverviewService(
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        evaluations=SQLiteEvaluationRepository(db_path),
        proposals=SQLiteIssueProposalRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
        reviews=SQLiteReviewRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _build_overview(db_path, proposal_id):
    return _service(db_path).build(
        proposal_id,
        "BIS Newsletter",
        EXTRACTORS,
        EVALUATORS,
        config_path=BIS_CONFIG,
        db_path=db_path,
    )


def _store_proposal(db_path, *, complete_evidence=True):
    articles = [Article(title="First article"), Article(title="Second article")]
    article_repo = SQLiteArticleRepository(db_path)
    for article in articles:
        article_repo.upsert(article)
    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
    )
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id for article in articles],
        objective_value=75,
        metadata={"optimisation_request_id": str(request.id)},
    )
    SQLiteIssueProposalRepository(db_path).insert(proposal)
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            event_type="proposal-created",
        )
    )
    selected = articles if complete_evidence else articles[:1]
    for article in selected:
        SQLiteExtractionRepository(db_path).insert(
            Extraction(
                article_id=article.id,
                extractor="reading_time",
                kind="reading_time",
                payload={"reading_minutes": 2},
            )
        )
        SQLiteEvaluationRepository(db_path).insert(
            Evaluation(
                article_id=article.id,
                evaluator="rule_relevance",
                kind="relevance",
                score=80,
            )
        )
    return articles, request, proposal


def _store_review(db_path, proposal, decision):
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=proposal.id,
        reviewer="Editor",
        decision=decision,
        comments="Editorial decision.",
    )
    SQLiteReviewRepository(db_path).insert(review)
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            event_type="review-submitted",
            payload={"review_id": str(review.id), "decision": decision.value},
        )
    )
    return review


def _store_publication(db_path, articles, proposal, review, *, rendered=False):
    publication = Publication(
        proposal_id=proposal.id,
        approved_review_id=review.id,
        title="BIS Newsletter",
        sections=[
            PublicationSection(
                heading="Lead",
                articles=[
                    PublicationArticle(
                        article_id=article.id,
                        title=article.title,
                    )
                    for article in articles
                ],
            )
        ],
    )
    SQLitePublicationRepository(db_path).insert(publication)
    events = SQLiteWorkflowEventRepository(db_path)
    events.insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-created",
        )
    )
    if rendered:
        events.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-published",
                payload={"format": "markdown", "output_path": "newsletter.md"},
            )
        )
    return publication


def test_overview_summarises_selected_article_evidence_and_pending_review(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _articles, request, proposal = _store_proposal(db_path, complete_evidence=False)

    overview = _build_overview(db_path, proposal.id)

    assert overview.optimisation_request == request
    assert overview.overall_status == "awaiting_review"
    assert overview.proposal_event_state == "draft"
    assert overview.extraction_coverage.expected_operations == 2
    assert overview.extraction_coverage.present == 1
    assert overview.extraction_coverage.missing == 1
    assert overview.evaluation_coverage.missing == 1
    assert [action.action for action in overview.outstanding_actions] == [
        "Complete extraction coverage",
        "Complete evaluation coverage",
        "Review the proposal",
    ]


def test_overview_prioritises_missing_article_records_before_processing(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, _request, _proposal = _store_proposal(db_path)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[articles[0].id, uuid4()],
        objective_value=50,
    )
    SQLiteIssueProposalRepository(db_path).insert(proposal)

    overview = _build_overview(db_path, proposal.id)

    assert len(overview.missing_article_ids) == 1
    assert [action.action for action in overview.outstanding_actions] == [
        "Investigate missing Articles",
        "Review the proposal",
    ]


def test_overview_derives_changes_requested_and_revision_action(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _articles, _request, proposal = _store_proposal(db_path)
    review = _store_review(db_path, proposal, ReviewDecision.NEEDS_CHANGES)

    overview = _build_overview(db_path, proposal.id)

    assert overview.overall_status == "changes_requested"
    assert next(
        stage for stage in overview.stages if stage.name == "Review"
    ).status == ("changes_requested")
    assert overview.outstanding_actions[-1].action == "Create a revision request"
    assert str(review.id) in overview.outstanding_actions[-1].command


def test_overview_links_revision_request_to_its_next_run(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _articles, request, proposal = _store_proposal(db_path)
    review = _store_review(db_path, proposal, ReviewDecision.NEEDS_CHANGES)
    revision = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        parent_request_id=request.id,
        parent_proposal_id=proposal.id,
        metadata={"source_review_id": str(review.id)},
    )
    SQLiteOptimisationRequestRepository(db_path).insert(revision)

    overview = _build_overview(db_path, proposal.id)

    assert overview.revision_requests == [revision]
    assert overview.outstanding_actions[-1].action == "Run the revision request"
    assert str(revision.id) in overview.outstanding_actions[-1].command


def test_overview_moves_from_approval_to_composition_to_rendering(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, _request, proposal = _store_proposal(db_path)
    review = _store_review(db_path, proposal, ReviewDecision.APPROVE)

    approved = _build_overview(db_path, proposal.id)
    publication = _store_publication(db_path, articles, proposal, review)
    composed = _build_overview(db_path, proposal.id)
    SQLiteWorkflowEventRepository(db_path).insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-published",
            payload={"format": "markdown", "output_path": "newsletter.md"},
        )
    )
    rendered = _build_overview(db_path, proposal.id)

    assert approved.overall_status == "approved"
    assert approved.outstanding_actions[-1].action == (
        "Compose the approved publication"
    )
    assert composed.overall_status == "composed"
    assert composed.outstanding_actions[-1].action == "Render the publication"
    assert rendered.overall_status == "rendered"
    assert rendered.outstanding_actions == []
    assert rendered.publications[0].rendered_output_count == 1


def test_overview_does_not_treat_publication_from_an_older_approval_as_current(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"
    articles, _request, proposal = _store_proposal(db_path)
    first_review = _store_review(db_path, proposal, ReviewDecision.APPROVE)
    _store_publication(db_path, articles, proposal, first_review, rendered=True)
    latest_review = _store_review(db_path, proposal, ReviewDecision.APPROVE)

    overview = _build_overview(db_path, proposal.id)

    assert overview.overall_status == "approved"
    assert overview.outstanding_actions[-1].action == (
        "Compose the approved publication"
    )
    assert str(latest_review.id) in overview.outstanding_actions[-1].command


def test_cli_workflow_overview_renders_stages_coverage_and_actions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    for command in ("ingest", "extract", "evaluate", "optimise"):
        result = runner.invoke(
            app, [command, "--config", BIS_CONFIG, "--db", str(db_path)]
        )
        assert result.exit_code == 0
    proposal = SQLiteIssueProposalRepository(db_path).list()[0]

    result = runner.invoke(
        app,
        [
            "workflow",
            "overview",
            "--proposal-id",
            str(proposal.id),
            "--config",
            BIS_CONFIG,
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Workflow Overview" in result.stdout
    assert "Issue Stages" in result.stdout
    assert "Extraction Coverage" in result.stdout
    assert "Evaluation Coverage" in result.stdout
    assert "100.0%" in result.stdout
    assert "awaiting_review" in result.stdout
    assert "Review the proposal" in result.stdout


def test_cli_workflow_overview_requires_existing_proposal(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "overview",
            "--proposal-id",
            str(uuid4()),
            "--config",
            BIS_CONFIG,
            "--db",
            str(tmp_path / "test.sqlite"),
        ],
    )

    assert result.exit_code == 2
    assert "Issue proposal not found" in result.output
