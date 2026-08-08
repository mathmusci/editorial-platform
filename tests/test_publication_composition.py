from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.composition import (
    CompositionArticle,
    CompositionExclusion,
    CompositionSection,
    PublicationComposition,
    PublicationCompositionService,
)
from editorial.models import (
    Article,
    Extraction,
    IssueProposal,
    Review,
    ReviewDecision,
)
from editorial.publishing import MarkdownPublisher
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> PublicationCompositionService:
    return PublicationCompositionService(
        proposals=SQLiteIssueProposalRepository(db_path),
        reviews=SQLiteReviewRepository(db_path),
        publications=SQLitePublicationRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        extractions=SQLiteExtractionRepository(db_path),
    )


def _store_fixture(db_path, *, decision=ReviewDecision.APPROVE):
    articles = [
        Article(
            title="Policy decision",
            summary="Original article summary.",
            source="BIS",
            url="https://example.org/policy",
        ),
        Article(title="Market resilience", source="BIS"),
        Article(title="Duplicate analysis", source="Partner"),
    ]
    article_repo = SQLiteArticleRepository(db_path)
    for article in articles:
        article_repo.upsert(article)

    extraction = Extraction(
        article_id=articles[0].id,
        extractor="local_summary",
        kind="summary",
        payload={"summary": "Stored extracted summary."},
    )
    SQLiteExtractionRepository(db_path).insert(extraction)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id for article in articles],
        objective_value=81,
    )
    SQLiteIssueProposalRepository(db_path).insert(proposal)
    review = Review(
        artefact_type="issue_proposal",
        artefact_id=proposal.id,
        reviewer="Editor",
        decision=decision,
        comments="Ready for composition.",
    )
    SQLiteReviewRepository(db_path).insert(review)
    return articles, extraction, proposal, review


def _composition(articles, extraction) -> PublicationComposition:
    return PublicationComposition(
        title="BIS Newsletter",
        subtitle="August 2026",
        introduction="This issue examines policy and resilience.",
        sections=[
            CompositionSection(
                heading="Lead analysis",
                introduction="The principal development this month.",
                articles=[
                    CompositionArticle(
                        article_id=articles[0].id,
                        title="What the policy decision means",
                        summary_extraction_id=extraction.id,
                    ),
                    CompositionArticle(
                        article_id=articles[1].id,
                        summary="An editor-written summary.",
                    ),
                ],
            )
        ],
        excluded=[
            CompositionExclusion(
                article_id=articles[2].id,
                reason="Duplicates the lead analysis.",
            )
        ],
        metadata={"edition": "monthly"},
    )


def test_composition_creates_approved_publication_with_content_snapshots(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)

    publication = _service(db_path).compose(
        proposal.id,
        review.id,
        _composition(articles, extraction),
        created_by="Composition editor",
    )

    item = publication.sections[0].articles[0]
    assert publication.approved_review_id == review.id
    assert publication.created_by == "Composition editor"
    assert publication.introduction == "This issue examines policy and resilience."
    assert item.article_id == articles[0].id
    assert item.title == "What the policy decision means"
    assert item.summary == "Stored extracted summary."
    assert item.source == "BIS"
    assert item.url == "https://example.org/policy"
    assert item.summary_extraction_id == extraction.id
    assert publication.exclusions[0].reason == "Duplicates the lead analysis."
    assert publication.metadata["article_count"] == 2
    assert SQLitePublicationRepository(db_path).get(publication.id) == publication


def test_composed_publication_renders_snapshots_after_article_changes(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    publication = _service(db_path).compose(
        proposal.id, review.id, _composition(articles, extraction)
    )
    changed_article = articles[0].model_copy(
        update={
            "title": "Changed database title",
            "summary": "Changed database summary.",
            "source": "Changed source",
        }
    )

    markdown = MarkdownPublisher([changed_article]).render(publication)

    assert "What the policy decision means" in markdown
    assert "Stored extracted summary." in markdown
    assert "Source: BIS - https://example.org/policy" in markdown
    assert "Changed database" not in markdown


def test_composition_records_parent_publication_lineage(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    parent = _service(db_path).compose(
        proposal.id, review.id, _composition(articles, extraction)
    )

    revision = _service(db_path).compose(
        proposal.id,
        review.id,
        _composition(articles, extraction),
        parent_publication_id=parent.id,
    )

    assert revision.parent_publication_id == parent.id
    assert SQLitePublicationRepository(db_path).count() == 2
    parent_show = CliRunner().invoke(
        app, ["publication", "show", str(parent.id), "--db", str(db_path)]
    )
    revision_show = CliRunner().invoke(
        app, ["publication", "show", str(revision.id), "--db", str(db_path)]
    )
    assert parent_show.exit_code == 0
    assert str(revision.id) in parent_show.stdout
    assert revision_show.exit_code == 0
    assert str(parent.id) in revision_show.stdout


def test_composition_requires_an_approving_review_for_the_proposal(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(
        db_path, decision=ReviewDecision.NEEDS_CHANGES
    )

    with pytest.raises(ValueError, match="requires an approve review"):
        _service(db_path).compose(
            proposal.id, review.id, _composition(articles, extraction)
        )


def test_composition_rejects_approval_for_another_proposal(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, _review = _store_fixture(db_path)
    other_review = Review(
        artefact_type="issue_proposal",
        artefact_id=uuid4(),
        reviewer="Other editor",
        decision=ReviewDecision.APPROVE,
    )
    SQLiteReviewRepository(db_path).insert(other_review)

    with pytest.raises(ValueError, match="must review the selected issue proposal"):
        _service(db_path).compose(
            proposal.id, other_review.id, _composition(articles, extraction)
        )


def test_composition_requires_every_proposal_article_to_be_accounted_for(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    incomplete = _composition(articles, extraction).model_copy(update={"excluded": []})

    with pytest.raises(ValueError, match="included or explicitly excluded"):
        _service(db_path).compose(proposal.id, review.id, incomplete)


def test_composition_rejects_duplicate_article_placement(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    composition = _composition(articles, extraction)
    duplicated_section = composition.sections[0].model_copy(
        update={
            "articles": [
                *composition.sections[0].articles,
                CompositionArticle(article_id=articles[0].id),
            ]
        }
    )
    duplicated = composition.model_copy(update={"sections": [duplicated_section]})

    with pytest.raises(ValueError, match="included more than once"):
        _service(db_path).compose(proposal.id, review.id, duplicated)


def test_composition_rejects_summary_extraction_from_another_article(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    composition = _composition(articles, extraction)
    wrong_item = CompositionArticle(
        article_id=articles[1].id,
        summary_extraction_id=extraction.id,
    )
    section = composition.sections[0].model_copy(
        update={"articles": [composition.sections[0].articles[0], wrong_item]}
    )
    invalid = composition.model_copy(update={"sections": [section]})

    with pytest.raises(ValueError, match="does not belong to article"):
        _service(db_path).compose(proposal.id, review.id, invalid)


def test_cli_composes_inspects_and_records_workflow(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, extraction, proposal, review = _store_fixture(db_path)
    composition_path = tmp_path / "composition.yaml"
    composition_path.write_text(
        f"""
title: BIS Newsletter
subtitle: August 2026
introduction: An editor-composed issue.
sections:
  - heading: Lead analysis
    introduction: The lead stories.
    articles:
      - article_id: {articles[0].id}
        title: Editorial policy headline
        summary_extraction_id: {extraction.id}
      - article_id: {articles[1].id}
        summary: An edited market summary.
excluded:
  - article_id: {articles[2].id}
    reason: Duplicates the lead analysis.
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "publication",
            "compose",
            "--proposal-id",
            str(proposal.id),
            "--approved-review-id",
            str(review.id),
            "--composition",
            str(composition_path),
            "--created-by",
            "Composition editor",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Created composed publication" in result.stdout
    assert "Included articles: 2" in result.stdout
    assert "Excluded articles: 1" in result.stdout
    publication = SQLitePublicationRepository(db_path).list()[0]
    assert publication.metadata["composition_source"] == str(composition_path)
    show = CliRunner().invoke(
        app, ["publication", "show", str(publication.id), "--db", str(db_path)]
    )
    assert show.exit_code == 0
    assert "Composition editor" in show.stdout
    assert "Editorial policy headline" in show.stdout
    assert "Explicit Exclusions" in show.stdout
    assert "Duplicates the lead analysis" in show.stdout
    assert "Approving editor" in show.stdout
    events = SQLiteWorkflowEventRepository(db_path).list(
        artefact_type="publication", artefact_id=publication.id
    )
    assert events[0].actor == "Composition editor"
    assert events[0].payload["approved_review_id"] == str(review.id)


def test_cli_composition_error_does_not_store_partial_publication(tmp_path):
    db_path = tmp_path / "test.sqlite"
    articles, _extraction, proposal, review = _store_fixture(db_path)
    composition_path = tmp_path / "composition.yaml"
    composition_path.write_text(
        f"""
title: Incomplete issue
sections:
  - heading: Lead
    articles:
      - article_id: {articles[0].id}
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "publication",
            "compose",
            "--proposal-id",
            str(proposal.id),
            "--approved-review-id",
            str(review.id),
            "--composition",
            str(composition_path),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 2
    assert "included or explicitly excluded" in result.output
    assert SQLitePublicationRepository(db_path).count() == 0
