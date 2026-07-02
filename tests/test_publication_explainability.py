from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.explain import PublicationExplanationService
from editorial.inspection import PublicationInspectionService
from editorial.models import (
    Article,
    ConstraintResult,
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


def _inspection_service(db_path) -> PublicationInspectionService:
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


def _service(db_path) -> PublicationExplanationService:
    return PublicationExplanationService(_inspection_service(db_path))


def _store_publication_fixture(
    db_path,
    *,
    with_review: bool = True,
    with_review_comments: bool = True,
    with_rendered_output: bool = True,
    with_workflow: bool = True,
    with_extractions: bool = True,
    with_evaluations: bool = True,
) -> tuple[Publication, IssueProposal, OptimisationRequest, list[Article]]:
    first = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
    )
    second = Article(
        title="Manufacturing output",
        url="https://example.org/manufacturing-output",
        source="Second Source",
    )
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(first)
    article_repo.upsert(second)

    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 2},
    )
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[first.id, second.id],
        objective_value=72.5,
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
                name="reading_time_target_minutes",
                kind="soft",
                satisfied=False,
                value=7,
                target=10,
                penalty=3,
            ),
        ],
        metadata={"optimisation_request_id": str(request.id)},
    )
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    SQLiteIssueProposalRepository(db_path).insert(proposal)

    publication = Publication(
        proposal_id=proposal.id,
        title="BIS Newsletter",
        subtitle="Draft issue",
        sections=[
            PublicationSection(
                heading="Selected articles",
                article_ids=[first.id, second.id],
            )
        ],
        metadata={"article_count": 2, "format": "newsletter"},
    )
    SQLitePublicationRepository(db_path).insert(publication)

    if with_extractions:
        extraction_repo = SQLiteExtractionRepository(db_path)
        extraction_repo.insert(
            Extraction(
                article_id=first.id,
                extractor="reading_time",
                kind="reading_time",
                payload={"reading_minutes": 4, "word_count": 700},
            )
        )
        extraction_repo.insert(
            Extraction(
                article_id=second.id,
                extractor="reading_time",
                kind="reading_time",
                payload={"reading_minutes": 3, "word_count": 500},
            )
        )

    if with_evaluations:
        evaluation_repo = SQLiteEvaluationRepository(db_path)
        evaluation_repo.insert(
            Evaluation(
                article_id=first.id,
                evaluator="rule_relevance",
                kind="relevance",
                score=80,
                rationale="Relevant statistics.",
            )
        )
        evaluation_repo.insert(
            Evaluation(
                article_id=second.id,
                evaluator="rule_relevance",
                kind="relevance",
                score=90,
                rationale="Relevant output data.",
            )
        )

    if with_review:
        SQLiteReviewRepository(db_path).insert(
            Review(
                artefact_type="issue_proposal",
                artefact_id=proposal.id,
                reviewer="Andy",
                decision=ReviewDecision.APPROVE,
                comments="Ready to publish" if with_review_comments else None,
            )
        )

    if with_workflow:
        workflow_repo = SQLiteWorkflowEventRepository(db_path)
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="issue_proposal",
                artefact_id=proposal.id,
                event_type="proposal-created",
                actor="optimiser",
            )
        )
        workflow_repo.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-created",
                actor="CLI",
            )
        )
        if with_rendered_output:
            workflow_repo.insert(
                WorkflowEvent(
                    artefact_type="publication",
                    artefact_id=publication.id,
                    event_type="publication-published",
                    actor="CLI",
                    payload={"format": "markdown", "output_path": "newsletter.md"},
                )
            )

    return publication, proposal, request, [first, second]


def test_service_builds_publication_explanation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, proposal, request, _articles = _store_publication_fixture(db_path)

    explanation = _service(db_path).get(publication.id)

    assert explanation is not None
    assert explanation.identity.publication_id == publication.id
    assert explanation.identity.proposal_id == proposal.id
    assert explanation.identity.optimisation_request_id == request.id
    assert explanation.composition.article_count == 2


def test_cli_explain_publication_works(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Publication Identity" in result.stdout
    assert "Editorial Summary" in result.stdout


def test_publication_identity_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, proposal, request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(publication.id) in result.stdout
    assert "BIS Newsletter" in result.stdout
    assert "Draft issue" in result.stdout
    assert str(proposal.id) in result.stdout
    assert str(request.id) in result.stdout


def test_editorial_summary_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "created from IssueProposal" in result.stdout
    assert str(proposal.id) in result.stdout
    assert "The proposal selected 2 articles." in result.stdout
    assert "The publication contains" in result.stdout
    assert "1 section" in result.stdout
    assert "2 articles" in result.stdout


def test_workflow_chronology_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Editorial Workflow" in result.stdout
    assert "Proposal created" in result.stdout
    assert "Publication created" in result.stdout
    assert "Publication published" in result.stdout


def test_review_linkage_and_comments_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "approve" in result.stdout
    assert "Ready to publish" in result.stdout


def test_composition_article_counts_and_source_counts_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Publication Composition" in result.stdout
    assert "Article count" in result.stdout
    assert "2" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "Second Source" in result.stdout


def test_reading_time_and_relevance_aggregates_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Total reading minutes" in result.stdout
    assert "7" in result.stdout
    assert "Average relevance score" in result.stdout
    assert "85.0" in result.stdout


def test_editorial_evidence_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Editorial Evidence" in result.stdout
    assert "Proposal objective value" in result.stdout
    assert "72.5" in result.stdout
    assert "Satisfied constraints" in result.stdout
    assert "Failed constraints" in result.stdout
    assert "reading_time_target_minutes" in result.stdout
    assert "article_count" in result.stdout


def test_interpretation_and_limitations_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "This publication reflects the stored Publication artefact." in result.stdout
    assert "limited to stored artefacts" in result.stdout


def test_missing_evaluations_handled(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(
        db_path, with_evaluations=False
    )

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Missing evaluations" in result.stdout
    assert "2 articles have missing evaluations." in result.stdout


def test_missing_extractions_handled(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(
        db_path, with_extractions=False
    )

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Missing reading time" in result.stdout
    assert "2 articles have missing reading-time data." in result.stdout


def test_missing_review_comments_handled(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(
        db_path, with_review_comments=False
    )

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No review comments recorded." in result.stdout


def test_missing_rendered_outputs_handled(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(
        db_path, with_rendered_output=False
    )

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "No rendered outputs recorded." in result.stdout


def test_related_artefacts_shown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, proposal, request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Related Artefacts" in result.stdout
    assert str(publication.id) in result.stdout
    assert str(proposal.id) in result.stdout
    assert str(request.id) in result.stdout
    assert "newsletter.md" in result.stdout


def test_output_does_not_infer_editorial_intent(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication, _proposal, _request, _articles = _store_publication_fixture(db_path)

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "The editor wanted" not in result.stdout
    assert "The publication focuses on" not in result.stdout
    assert "The optimiser believed" not in result.stdout
    assert "The publication achieves" not in result.stdout


def test_invalid_publication_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    publication_id = uuid4()

    result = CliRunner().invoke(
        app, ["explain", "publication", str(publication_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Publication not found: {publication_id}" in result.stdout
