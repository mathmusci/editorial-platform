import time
import pytest
from uuid import uuid4

from fastapi.testclient import TestClient
from typer.main import get_command
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


def test_generate_first_issue_from_workspace(tmp_path):
    db = tmp_path / "first-issue.sqlite"
    client = TestClient(create_app(CONFIG, db))
    article = Article(title="Industrial statistics", source="BIS")
    SQLiteArticleRepository(db).insert(article)
    SQLiteEvaluationRepository(db).insert(
        Evaluation(
            article_id=article.id,
            evaluator="rule_relevance",
            kind="relevance",
            score=90,
            confidence=1,
        )
    )
    empty = client.get("/proposals")
    assert "No issue proposals" in empty.text
    assert "Generate issue proposal" in empty.text
    assert client.post("/proposals/generate").status_code == 403
    assert SQLiteOptimisationRequestRepository(db).count() == 0
    response = client.post(
        "/proposals/generate",
        data={
            "csrf_token": client.app.state.csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    proposal = SQLiteIssueProposalRepository(db).list()[0]
    assert response.headers["location"] == f"/proposals/{proposal.id}"
    assert article.id in proposal.article_ids
    saved = SQLiteOptimisationRequestRepository(db).list()[0]
    assert saved.settings == client.app.state.workspace.config.optimisation.settings
    assert proposal.metadata["optimisation_request_id"] == str(saved.id)
    assert client.get(response.headers["location"]).status_code == 200
    assert "Generate issue proposal" in client.get("/proposals").text


def test_generation_failure_is_visible_and_retains_request(tmp_path, monkeypatch):
    import editorial.optimisation_service as optimisation

    def fail(request, db):
        raise ValueError("Unsupported optimisation strategy")

    monkeypatch.setattr(optimisation, "run_optimisation_request", fail)
    db = tmp_path / "failure.sqlite"
    client = TestClient(create_app(CONFIG, db))
    response = client.post(
        "/proposals/generate",
        data={
            "csrf_token": client.app.state.csrf_token,
        },
    )
    assert response.status_code == 400
    assert (
        "Proposal generation failed: Unsupported optimisation strategy" in response.text
    )
    assert "Traceback" not in response.text
    assert SQLiteOptimisationRequestRepository(db).count() == 1
    assert SQLiteIssueProposalRepository(db).count() == 0


@pytest.mark.parametrize("decision", ["approve", "reject", "needs_changes", "comment"])
def test_submit_editorial_review(tmp_path, decision):
    client, _, proposal, _, _ = _workspace(tmp_path)
    before = client.app.state.workspace.reviews.proposals.get(proposal.id)
    response = client.post(
        f"/proposals/{proposal.id}/review",
        data={
            "csrf_token": client.app.state.csrf_token,
            "reviewer": "Morgan",
            "decision": decision,
            "comments": "Editorial assessment",
            "findings": "Coverage is narrow",
            "recommendations": "Broaden sources",
        },
    )
    assert response.status_code == 200
    assert "Coverage is narrow" in response.text
    assert "Broaden sources" in response.text
    repository = client.app.state.workspace.reviews
    stored = repository.reviews.list(artefact_id=proposal.id)[-1]
    assert stored.decision.value == decision
    assert stored.findings == {"notes": "Coverage is narrow"}
    assert repository.proposals.get(proposal.id) == before
    events = repository.workflow_events.list(artefact_id=proposal.id)
    assert any(e.payload.get("review_id") == str(stored.id) for e in events)


def test_review_revision_candidate_and_comparison(tmp_path):
    client, _, proposal, _, _ = _workspace(tmp_path)
    token = client.app.state.csrf_token
    response = client.post(
        f"/proposals/{proposal.id}/review",
        data={
            "csrf_token": token,
            "reviewer": "Morgan",
            "decision": "needs_changes",
        },
        follow_redirects=False,
    )
    review_url = response.headers["location"]
    revision = client.post(
        f"{review_url}/revise",
        data={
            "csrf_token": token,
            "settings": '{"max_articles": 1}',
        },
        follow_redirects=False,
    )
    assert revision.status_code == 303
    revision_url = revision.headers["location"]
    detail = client.get(revision_url)
    assert "Generate candidate proposal" in detail.text
    generated = client.post(f"{revision_url}/run", data={"csrf_token": token})
    assert generated.status_code == 200
    assert "Compare with original" in generated.text
    repository = client.app.state.workspace.reviews
    candidates = [p for p in repository.proposals.list() if p.id != proposal.id]
    assert len(candidates) == 1
    compare = client.get(
        f"/proposals/compare?base={proposal.id}&candidate={candidates[0].id}"
    )
    assert compare.status_code == 200
    assert "Selection changes" in compare.text
    saved = repository.optimisation_requests.get(revision_url.rsplit("/", 1)[-1])
    assert saved.parent_proposal_id == proposal.id
    assert saved.settings["max_articles"] == 1


def test_review_forms_reject_invalid_input_and_preserve_text(tmp_path):
    client, _, proposal, review, _ = _workspace(tmp_path)
    url = f"/proposals/{proposal.id}/review"
    assert client.post(url).status_code == 403
    response = client.post(
        url,
        data={
            "csrf_token": client.app.state.csrf_token,
            "reviewer": "  ",
            "decision": "approve",
            "comments": "Keep my draft",
        },
    )
    assert response.status_code == 400
    assert "Keep my draft" in response.text
    rejected = client.post(
        f"/reviews/{review.id}/revise",
        data={
            "csrf_token": client.app.state.csrf_token,
        },
    )
    assert rejected.status_code == 400
    assert client.post(f"/revision-requests/{uuid4()}/run").status_code == 403


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


def test_workspace_starts_and_inspects_durable_pipeline_operation(tmp_path):
    client, _articles, _proposal, _review, _publication = _workspace(tmp_path)

    operation_list = client.get("/operations")
    response = client.post(
        "/operations",
        data={
            "csrf_token": client.app.state.csrf_token,
            "kind": "extract",
            "limit": "1",
            "offset": "1",
            "missing_only": "on",
        },
        follow_redirects=False,
    )

    assert operation_list.status_code == 200
    assert "Pipeline operations" in operation_list.text
    assert "Start ingestion" in operation_list.text
    assert response.status_code == 303
    run_id = response.headers["location"].rsplit("/", 1)[-1]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        run = client.app.state.workspace.processing.runs.get(run_id)
        if run is not None and not run.active:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Pipeline operation did not finish")

    detail = client.get(response.headers["location"])
    history = client.get("/operations")
    assert run.status == "completed"
    assert run.options.limit == 1
    assert run.options.offset == 1
    assert run.options.missing_only is True
    assert detail.status_code == 200
    assert "Run options" in detail.text
    assert "Execution context" in detail.text
    assert run_id in detail.text
    assert run_id[:8] in history.text


def test_workspace_guards_pipeline_operation_forms(tmp_path):
    client, _articles, _proposal, _review, _publication = _workspace(tmp_path)

    missing_token = client.post(
        "/operations", data={"kind": "extract"}, follow_redirects=False
    )
    incompatible = client.post(
        "/operations",
        data={
            "csrf_token": client.app.state.csrf_token,
            "kind": "extract",
            "missing_only": "on",
            "force": "on",
        },
        follow_redirects=False,
    )

    assert missing_token.status_code == 403
    assert "Invalid form token" in missing_token.text
    assert incompatible.status_code == 400
    assert "missing_only and force cannot be used together" in incompatible.text


def test_web_command_is_available():
    result = CliRunner().invoke(cli_app, ["web", "--help"])
    command = get_command(cli_app).commands["web"]
    option_names = {
        option
        for parameter in command.params
        for option in getattr(parameter, "opts", [])
    }

    assert result.exit_code == 0
    assert {"--config", "--host", "--port"} <= option_names
