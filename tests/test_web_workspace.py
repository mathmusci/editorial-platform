from uuid import uuid4

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from editorial.cli import app as cli_app
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
from editorial.web import create_app

CONFIG = "tests/fixtures/bis/publication.yaml"


def _workspace(tmp_path):
    db_path = tmp_path / "workspace.sqlite"
    articles = [
        Article(
            title="Industrial production strengthens",
            source="BIS",
            url="https://example.com/industrial-production",
            summary="Production increased across several sectors.",
        ),
        Article(
            title="Trade statistics update",
            source="BIS",
            summary="Recent changes in international trade.",
        ),
    ]
    article_repository = SQLiteArticleRepository(db_path)
    extraction_repository = SQLiteExtractionRepository(db_path)
    evaluation_repository = SQLiteEvaluationRepository(db_path)
    for article in articles:
        article_repository.insert(article)
        extraction_repository.insert(
            Extraction(
                article_id=article.id,
                extractor="reading_time",
                kind="reading_time",
                payload={"reading_minutes": 3, "word_count": 530},
            )
        )
        evaluation_repository.insert(
            Evaluation(
                article_id=article.id,
                evaluator="rule_relevance",
                kind="relevance",
                score=82,
                confidence=1,
                rationale="Matches the publication's statistical focus.",
            )
        )

    request = OptimisationRequest(publication="BIS Newsletter", strategy="greedy")
    SQLiteOptimisationRequestRepository(db_path).insert(request)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id for article in articles],
        objective_value=164,
        metadata={"optimisation_request_id": str(request.id)},
    )
    SQLiteIssueProposalRepository(db_path).insert(proposal)
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=proposal.id,
        reviewer="Alex Editor",
        decision=ReviewDecision.APPROVE,
        comments="The selection is balanced and ready to compose.",
    )
    SQLiteReviewRepository(db_path).insert(review)
    publication = Publication(
        proposal_id=proposal.id,
        approved_review_id=review.id,
        title="BIS Newsletter",
        subtitle="Statistics for informed decisions",
        sections=[
            PublicationSection(
                heading="The week in statistics",
                introduction="A concise view of the latest evidence.",
                articles=[
                    PublicationArticle(
                        article_id=article.id,
                        title=article.title,
                        summary=article.summary,
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
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            event_type="proposal-created",
        )
    )
    events.insert(
        WorkflowEvent(
            artefact_type="issue_proposal",
            artefact_id=proposal.id,
            event_type="review-submitted",
            payload={"review_id": str(review.id), "decision": "approve"},
        )
    )
    events.insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-created",
        )
    )
    events.insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-published",
            payload={"format": "markdown", "output_path": "newsletter.md"},
        )
    )
    client = TestClient(create_app(CONFIG, db_path))
    return client, articles, proposal, review, publication


def test_workspace_redirects_to_issue_proposals(tmp_path):
    client, _articles, _proposal, _review, _publication = _workspace(tmp_path)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/proposals"


def test_workspace_lists_and_inspects_complete_issue(tmp_path):
    client, articles, proposal, review, publication = _workspace(tmp_path)

    proposal_list = client.get("/proposals")
    proposal_detail = client.get(f"/proposals/{proposal.id}")

    assert proposal_list.status_code == 200
    assert "Editorial issues" in proposal_list.text
    assert str(proposal.id) in proposal_list.text
    assert proposal_detail.status_code == 200
    assert "Workflow status" in proposal_detail.text
    assert "Processor coverage" in proposal_detail.text
    assert articles[0].title in proposal_detail.text
    assert f"/articles/{articles[0].id}" in proposal_detail.text
    assert f"/reviews/{review.id}" in proposal_detail.text
    assert f"/publications/{publication.id}" in proposal_detail.text


def test_workspace_renders_article_evidence_and_provenance_payload(tmp_path):
    client, articles, _proposal, _review, _publication = _workspace(tmp_path)

    response = client.get(f"/articles/{articles[0].id}")

    assert response.status_code == 200
    assert "Article evidence" in response.text
    assert "reading time" in response.text
    assert "3" in response.text
    assert "Matches the publication" in response.text
    assert "Full payload" in response.text


def test_workspace_lists_and_inspects_reviews_and_publications(tmp_path):
    client, articles, proposal, review, publication = _workspace(tmp_path)

    review_list = client.get("/reviews")
    review_detail = client.get(f"/reviews/{review.id}")
    publication_list = client.get("/publications")
    publication_detail = client.get(f"/publications/{publication.id}")

    assert review_list.status_code == 200
    assert "Alex Editor" in review_list.text
    assert review_detail.status_code == 200
    assert "balanced and ready" in review_detail.text
    assert f"/proposals/{proposal.id}" in review_detail.text
    assert publication_list.status_code == 200
    assert "Statistics for informed decisions" in publication_list.text
    assert publication_detail.status_code == 200
    assert "The week in statistics" in publication_detail.text
    assert articles[0].title in publication_detail.text


def test_workspace_compares_two_proposals(tmp_path):
    client, articles, proposal, _review, _publication = _workspace(tmp_path)
    candidate = IssueProposal(
        optimiser="greedy",
        article_ids=[articles[1].id],
        objective_value=90,
    )
    client.app.state.workspace.proposals.proposals.insert(candidate)

    response = client.get(
        "/proposals/compare",
        params={"base": proposal.id, "candidate": candidate.id},
    )

    assert response.status_code == 200
    assert "Selection changes" in response.text
    assert "removed" in response.text
    assert articles[0].title in response.text


def test_workspace_is_read_only_and_returns_friendly_missing_page(tmp_path):
    client, _articles, _proposal, _review, _publication = _workspace(tmp_path)

    assert client.post("/proposals").status_code == 405
    missing = client.get(f"/articles/{uuid4()}")
    assert missing.status_code == 404
    assert "Article not found" in missing.text
    assert "Return to issues" in missing.text


def test_workspace_static_styles_are_served(tmp_path):
    client, _articles, _proposal, _review, _publication = _workspace(tmp_path)

    response = client.get("/static/workspace.css")

    assert response.status_code == 200
    assert "--teal" in response.text


def test_workspace_displays_active_configuration(tmp_path):
    client, _articles, proposal, _review, _publication = _workspace(tmp_path)

    response = client.get("/configuration")
    proposal_response = client.get(f"/proposals/{proposal.id}")

    assert response.status_code == 200
    assert "Active configuration" in response.text
    assert "Current server configuration" in response.text
    assert "BIS fixture provider" in response.text
    assert "Reading time" in response.text
    assert "BIS relevance" in response.text
    assert "Maximum reading time" in response.text
    assert "greedy" in response.text
    assert "Normalized loaded YAML" in response.text
    assert 'href="/configuration"' in response.text
    assert 'href="/configuration#extractors-reading_time"' in (proposal_response.text)


def test_workspace_redacts_secret_values_from_configuration(tmp_path):
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(
        """
publication:
  name: Private publication
extractors:
  - type: llm_summary
    provider:
      type: ollama
      model: local-model
      api_token: do-not-display
      api_key_env: LOCAL_API_KEY
""".strip(),
        encoding="utf-8",
    )
    client = TestClient(create_app(config_path, tmp_path / "workspace.sqlite"))

    response = client.get("/configuration")

    assert response.status_code == 200
    assert "do-not-display" not in response.text
    assert "*** redacted ***" in response.text
    assert "LOCAL_API_KEY" in response.text


def test_web_command_is_available():
    result = CliRunner().invoke(cli_app, ["web", "--help"])

    assert result.exit_code == 0
    assert "--config" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout
