import re
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import ProposalComparisonService, ProposalInspectionService
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

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _unstyled(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _service(db_path) -> ProposalComparisonService:
    return ProposalComparisonService(
        ProposalInspectionService(
            proposals=SQLiteIssueProposalRepository(db_path),
            articles=SQLiteArticleRepository(db_path),
            extractions=SQLiteExtractionRepository(db_path),
            evaluations=SQLiteEvaluationRepository(db_path),
            optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
            workflow_events=SQLiteWorkflowEventRepository(db_path),
            reviews=SQLiteReviewRepository(db_path),
            publications=SQLitePublicationRepository(db_path),
        )
    )


def _snapshot(
    article: Article, *, relevance: float, reading: float
) -> dict[str, object]:
    return {
        "article_id": str(article.id),
        "relevance_score": relevance,
        "reading_minutes": reading,
        "mandatory_terms": [],
        "source": article.source,
    }


def _store_comparison_fixture(
    db_path,
) -> tuple[IssueProposal, IssueProposal, Article, Article, Article]:
    base_only = Article(title="Base only", source="Source A")
    shared = Article(title="Shared article", source="Source B")
    candidate_only = Article(title="Candidate only", source="Source C")
    articles = SQLiteArticleRepository(db_path)
    for article in (base_only, shared, candidate_only):
        articles.upsert(article)

    base_request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 2, "reading_time_target_minutes": 10},
        created_by="Editor",
    )
    candidate_request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={"max_articles": 2, "reading_time_target_minutes": 12},
        created_by="Editor",
        parent_request_id=base_request.id,
    )
    requests = SQLiteOptimisationRequestRepository(db_path)
    requests.insert(base_request)
    requests.insert(candidate_request)

    unchanged_constraint = ConstraintResult(
        name="max_articles",
        kind="hard",
        satisfied=True,
        value=2,
        target=2,
    )
    base = IssueProposal(
        optimiser="greedy",
        optimiser_version="0.1.0",
        article_ids=[base_only.id, shared.id],
        objective_value=150,
        constraint_results=[
            unchanged_constraint,
            ConstraintResult(
                name="reading_time_target_minutes",
                kind="goal",
                satisfied=False,
                value=7,
                target=10,
                penalty=9,
            ),
        ],
        metadata={
            "optimisation_request_id": str(base_request.id),
            "selected": [
                _snapshot(base_only, relevance=80, reading=3),
                _snapshot(shared, relevance=70, reading=4),
            ],
        },
    )
    candidate = IssueProposal(
        optimiser="greedy",
        optimiser_version="0.1.0",
        article_ids=[shared.id, candidate_only.id],
        objective_value=155,
        constraint_results=[
            unchanged_constraint,
            ConstraintResult(
                name="reading_time_target_minutes",
                kind="goal",
                satisfied=False,
                value=11,
                target=12,
                penalty=3,
            ),
        ],
        metadata={
            "optimisation_request_id": str(candidate_request.id),
            "selected": [
                _snapshot(shared, relevance=75, reading=5),
                _snapshot(candidate_only, relevance=90, reading=6),
            ],
        },
    )
    proposals = SQLiteIssueProposalRepository(db_path)
    proposals.insert(base)
    proposals.insert(candidate)
    return base, candidate, base_only, shared, candidate_only


def test_service_compares_membership_order_and_proposal_evidence(tmp_path):
    db_path = tmp_path / "test.sqlite"
    base, candidate, base_only, shared, candidate_only = _store_comparison_fixture(
        db_path
    )

    report = _service(db_path).compare(base.id, candidate.id)

    assert report.shared_articles == 1
    assert report.added_articles == 1
    assert report.removed_articles == 1
    assert report.moved_articles == 1
    assert report.objective_delta == 5
    assert report.base.known_reading_minutes == 7
    assert report.candidate.known_reading_minutes == 11
    assert report.evidence_gaps == []

    by_id = {article.article_id: article for article in report.articles}
    assert by_id[base_only.id].status == "removed"
    assert by_id[candidate_only.id].status == "added"
    assert by_id[shared.id].status == "shared"
    assert by_id[shared.id].moved is True
    assert by_id[shared.id].base_position == 2
    assert by_id[shared.id].candidate_position == 1
    assert by_id[shared.id].base_evidence is not None
    assert by_id[shared.id].base_evidence.relevance_score == 70
    assert by_id[shared.id].candidate_evidence is not None
    assert by_id[shared.id].candidate_evidence.relevance_score == 75
    assert by_id[shared.id].base_evidence.origin == "proposal_snapshot"


def test_service_compares_request_fields_and_constraint_outcomes(tmp_path):
    db_path = tmp_path / "test.sqlite"
    base, candidate, *_articles = _store_comparison_fixture(db_path)

    report = _service(db_path).compare(base.id, candidate.id)

    differences = {
        difference.field: difference for difference in report.request_differences
    }
    assert differences["settings.reading_time_target_minutes"].base_value == 10
    assert differences["settings.reading_time_target_minutes"].candidate_value == 12
    assert differences["parent_request_id"].base_value is None
    assert differences["parent_request_id"].candidate_value is not None

    constraints = {item.name: item for item in report.constraints}
    assert constraints["max_articles"].status == "unchanged"
    assert constraints["reading_time_target_minutes"].status == "changed"
    assert constraints["reading_time_target_minutes"].base is not None
    assert constraints["reading_time_target_minutes"].base.penalty == 9
    assert constraints["reading_time_target_minutes"].candidate is not None
    assert constraints["reading_time_target_minutes"].candidate.penalty == 3


def test_service_labels_current_evidence_fallback_and_missing_lineage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = Article(title="Current evidence", source="Source")
    SQLiteArticleRepository(db_path).upsert(article)
    SQLiteExtractionRepository(db_path).insert(
        Extraction(
            article_id=article.id,
            extractor="reading_time",
            kind="reading_time",
            payload={"reading_minutes": 4},
        )
    )
    SQLiteEvaluationRepository(db_path).insert(
        Evaluation(
            article_id=article.id,
            evaluator="relevance",
            kind="relevance",
            score=82,
        )
    )
    missing_article_id = uuid4()
    base = IssueProposal(
        optimiser="legacy",
        article_ids=[article.id],
        objective_value=82,
    )
    candidate = IssueProposal(
        optimiser="legacy",
        article_ids=[article.id, missing_article_id],
        objective_value=82,
    )
    proposals = SQLiteIssueProposalRepository(db_path)
    proposals.insert(base)
    proposals.insert(candidate)

    report = _service(db_path).compare(base.id, candidate.id)

    current = next(item for item in report.articles if item.article_id == article.id)
    assert current.base_evidence is not None
    assert current.base_evidence.origin == "current_stored_evidence"
    assert current.base_evidence.reading_minutes == 4
    missing = next(
        item for item in report.articles if item.article_id == missing_article_id
    )
    assert missing.candidate_evidence is not None
    assert missing.candidate_evidence.origin == "missing"
    assert any(
        "current stored evidence is shown" in gap for gap in report.evidence_gaps
    )
    assert any("missing article" in gap for gap in report.evidence_gaps)
    assert any("no linked optimisation request" in gap for gap in report.evidence_gaps)


def test_service_rejects_same_or_unknown_proposal_ids(tmp_path):
    db_path = tmp_path / "test.sqlite"
    base, _candidate, *_articles = _store_comparison_fixture(db_path)

    with pytest.raises(ValueError, match="two different proposal IDs"):
        _service(db_path).compare(base.id, base.id)

    missing_id = uuid4()
    with pytest.raises(ValueError, match=f"Issue proposal not found: {missing_id}"):
        _service(db_path).compare(base.id, missing_id)


def test_cli_proposal_compare_renders_editorial_differences(tmp_path):
    db_path = tmp_path / "test.sqlite"
    base, candidate, *_articles = _store_comparison_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "proposal",
            "compare",
            str(base.id),
            str(candidate.id),
            "--db",
            str(db_path),
        ],
    )

    output = " ".join(_unstyled(result.stdout).replace("│", " ").split())
    assert result.exit_code == 0
    assert "Proposal Comparison" in output
    assert "Shared article" in output
    assert "Base only" in output
    assert "Candidate only" in output
    assert "shared, moved" in output
    assert "Optimisation Request Changes" in output
    assert "Settings.reading time target" in output
    assert "Constraint Outcomes" in output
    assert "No evidence gaps found" in output


def test_cli_proposal_compare_reports_missing_proposal_cleanly(tmp_path):
    missing_base = uuid4()
    missing_candidate = uuid4()

    result = CliRunner().invoke(
        app,
        [
            "proposal",
            "compare",
            str(missing_base),
            str(missing_candidate),
            "--db",
            str(tmp_path / "test.sqlite"),
        ],
    )

    output = " ".join(_unstyled(result.output).replace("│", " ").split())
    assert result.exit_code != 0
    assert f"Issue proposal not found: {missing_base}" in output
