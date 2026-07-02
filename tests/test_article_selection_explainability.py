from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.explain import ArticleSelectionExplanationService
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
)


def _service(db_path) -> ArticleSelectionExplanationService:
    return ArticleSelectionExplanationService(
        proposals=SQLiteIssueProposalRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
        evaluations=SQLiteEvaluationRepository(db_path),
        optimisation_requests=SQLiteOptimisationRequestRepository(db_path),
    )


def _store_selection_fixture(
    db_path,
    *,
    with_evidence: bool = True,
    with_constraints: bool = True,
) -> tuple[IssueProposal, OptimisationRequest, Article, Article]:
    included = Article(
        title="Industrial statistics selected",
        url="https://example.org/selected",
        source="Fixture Source",
        summary="Statistics and output data.",
    )
    excluded = Article(
        title="Industrial statistics not selected",
        url="https://example.org/not-selected",
        source="Fixture Source",
        summary="More statistics.",
    )
    request = OptimisationRequest(
        publication="BIS Newsletter",
        strategy="greedy",
        settings={
            "max_articles": 1,
            "reading_time_target_minutes": 5,
            "relevance_target_score": 70,
            "mandatory_terms": ["statistics"],
            "source_diversity_max_per_source": 1,
        },
    )
    constraints = []
    if with_constraints:
        constraints = [
            ConstraintResult(
                name="max_articles",
                kind="hard",
                satisfied=True,
                value=1,
                target=1,
                penalty=0,
            ),
            ConstraintResult(
                name="relevance_target_score",
                kind="soft",
                satisfied=True,
                value=85,
                target=70,
                penalty=0,
            ),
            ConstraintResult(
                name="reading_time_target_minutes",
                kind="soft",
                satisfied=False,
                value=4,
                target=5,
                penalty=3,
            ),
            ConstraintResult(
                name="source_diversity_max_per_source",
                kind="soft",
                satisfied=False,
                value={"Fixture Source": 1},
                target=1,
                penalty=2,
            ),
        ]
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[included.id],
        objective_value=80,
        constraint_results=constraints,
        metadata={"optimisation_request_id": str(request.id)},
    )

    articles = SQLiteArticleRepository(db_path)
    articles.upsert(included)
    articles.upsert(excluded)
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    SQLiteIssueProposalRepository(db_path).insert(proposal)

    if with_evidence:
        extractions = SQLiteExtractionRepository(db_path)
        evaluations = SQLiteEvaluationRepository(db_path)
        for article in [included, excluded]:
            extractions.insert(
                Extraction(
                    article_id=article.id,
                    extractor="reading_time",
                    kind="reading_time",
                    payload={"reading_minutes": 4, "word_count": 700},
                )
            )
            extractions.insert(
                Extraction(
                    article_id=article.id,
                    extractor="summary",
                    kind="summary",
                    payload={"summary": "A concise industrial statistics item."},
                )
            )
            evaluations.insert(
                Evaluation(
                    article_id=article.id,
                    evaluator="rule_relevance",
                    kind="relevance",
                    score=85,
                    confidence=0.9,
                    rationale="Matched include terms ['statistics'].",
                )
            )
    return proposal, request, included, excluded


def test_service_builds_explanation_for_included_article(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, request, included, _excluded = _store_selection_fixture(db_path)

    explanation = _service(db_path).get(proposal.id, included.id)

    assert explanation is not None
    assert explanation.proposal_id == proposal.id
    assert explanation.article_id == included.id
    assert explanation.optimisation_request_id == request.id
    assert explanation.outcome.included is True
    assert explanation.proposal_context.selected_article_count == 1


def test_service_builds_explanation_for_excluded_article(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _included, excluded = _store_selection_fixture(db_path)

    explanation = _service(db_path).get(proposal.id, excluded.id)

    assert explanation is not None
    assert explanation.outcome.included is False
    assert explanation.article_id == excluded.id
    assert explanation.proposal_context.article_source_represented is True


def test_cli_article_selection_explain_works(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Article Selection Identity" in result.stdout
    assert "Selection Outcome" in result.stdout


def test_output_states_included_article_was_included(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "This article is included in the stored proposal." in result.stdout


def test_output_states_excluded_article_was_not_included(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _included, excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(excluded.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "This article is not included in the stored proposal." in result.stdout
    assert (
        "The stored proposal does not record the exact exclusion reason"
        in result.stdout
    )


def test_output_includes_article_title_source_and_url(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Industrial statistics selected" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "https://example.org/selected" in result.stdout


def test_output_includes_relevance_score_and_rationale(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Score: 85.0" in result.stdout
    assert "Confidence: 0.9" in result.stdout
    assert "Matched include terms" in result.stdout


def test_output_includes_reading_time(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Reading minutes" in result.stdout
    assert "Word count" in result.stdout


def test_output_handles_missing_extraction_and_evaluation_data(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(
        db_path, with_evidence=False
    )

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "No extraction or evaluation evidence is available." in result.stdout


def test_output_includes_proposal_objective_and_selected_count(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Proposal objective value:" in result.stdout
    assert "80.0" in result.stdout
    assert "Selected article count" in result.stdout
    assert "1" in result.stdout
    assert "Sources represented" in result.stdout
    assert "Fixture Source" in result.stdout
    assert '{"Fixture Source"' not in result.stdout


def test_output_includes_constraint_context_where_recorded(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, included, _excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Constraint Context" in result.stdout
    assert "max_articles" in result.stdout
    assert "reading_time_target_minutes" in result.stdout
    assert "source_diversity_max_per_source" in result.stdout


def test_output_does_not_overclaim_exclusion_causality(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _included, excluded = _store_selection_fixture(db_path)

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(excluded.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "excluded because" not in result.stdout
    assert "rejected this article due to" not in result.stdout
    assert "would have improved the proposal" not in result.stdout


def test_invalid_proposal_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _proposal, _request, included, _excluded = _store_selection_fixture(db_path)
    proposal_id = uuid4()

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal_id),
            str(included.id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert f"Issue proposal not found: {proposal_id}" in result.stdout


def test_invalid_article_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    proposal, _request, _included, _excluded = _store_selection_fixture(db_path)
    article_id = uuid4()

    result = CliRunner().invoke(
        app,
        [
            "explain",
            "article-selection",
            str(proposal.id),
            str(article_id),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert f"Article not found: {article_id}" in result.stdout
