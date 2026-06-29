import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from editorial.cli import app
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    PublicationSection,
)
from editorial.publishing import MarkdownPublisher, PublicationBuilder
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteWorkflowEventRepository,
)


def test_publication_models_validate_and_are_immutable():
    article_id = uuid4()
    proposal_id = uuid4()
    section = PublicationSection(
        heading="Selected articles",
        article_ids=[article_id],
        summary="A short section",
        metadata={"kind": "selection"},
    )
    publication = Publication(
        proposal_id=proposal_id,
        title="BIS Newsletter",
        subtitle="Draft issue",
        sections=[section],
        metadata={"article_count": 1},
    )

    assert publication.proposal_id == proposal_id
    assert publication.sections == [section]

    with pytest.raises(ValidationError):
        PublicationSection(heading="")

    with pytest.raises(ValidationError):
        Publication(proposal_id=proposal_id, title="")

    with pytest.raises(ValidationError):
        publication.title = "Other"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        section.heading = "Other"  # type: ignore[misc]


def test_publication_repository_insert_get_list_count_and_no_workflow_event(tmp_path):
    db_path = tmp_path / "test.sqlite"
    repo = SQLitePublicationRepository(db_path)
    publication = Publication(
        proposal_id=uuid4(),
        title="BIS Newsletter",
        sections=[
            PublicationSection(heading="Selected articles", article_ids=[uuid4()])
        ],
        metadata={"article_count": 1},
    )

    repo.insert(publication)

    assert repo.count() == 1
    assert repo.get(publication.id) == publication
    assert repo.list() == [publication]
    assert SQLiteWorkflowEventRepository(db_path).count() == 0


def test_publication_repository_is_append_only(tmp_path):
    repo = SQLitePublicationRepository(tmp_path / "test.sqlite")
    proposal_id = uuid4()

    repo.insert(Publication(proposal_id=proposal_id, title="First"))
    repo.insert(Publication(proposal_id=proposal_id, title="Second"))

    assert repo.count() == 2


def test_publication_insert_duplicate_id_is_rejected(tmp_path):
    repo = SQLitePublicationRepository(tmp_path / "test.sqlite")
    publication = Publication(proposal_id=uuid4(), title="BIS Newsletter")

    repo.insert(publication)

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(publication)


def test_publication_builder_preserves_proposal_article_order_and_metadata():
    first = Article(title="First article")
    second = Article(title="Second article")
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[second.id, first.id],
        objective_value=42.5,
    )
    extraction = Extraction(
        article_id=first.id,
        extractor="reading_time",
        kind="reading_time",
        payload={"minutes": 4},
    )
    evaluation = Evaluation(
        article_id=second.id,
        evaluator="rule_relevance",
        kind="relevance",
        score=80,
    )

    publication = PublicationBuilder().build(
        proposal=proposal,
        articles=[first, second],
        extractions=[extraction],
        evaluations=[evaluation],
        title="BIS Newsletter",
        subtitle="Draft issue",
    )

    assert publication.proposal_id == proposal.id
    assert publication.title == "BIS Newsletter"
    assert publication.subtitle == "Draft issue"
    assert publication.sections[0].article_ids == [second.id, first.id]
    assert publication.metadata["proposal_id"] == str(proposal.id)
    assert publication.metadata["article_count"] == 2
    assert publication.metadata["optimiser"] == "greedy"
    assert publication.metadata["objective_value"] == 42.5
    assert publication.metadata["extraction_count"] == 1
    assert publication.metadata["evaluation_count"] == 1


def test_publication_builder_does_not_mutate_proposal():
    article = Article(title="Article")
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id],
        objective_value=10,
        metadata={"source": "test"},
    )

    PublicationBuilder().build(
        proposal=proposal,
        articles=[article],
        extractions=[],
        evaluations=[],
        title="BIS Newsletter",
    )

    assert proposal == IssueProposal.model_validate(proposal.model_dump())


def test_markdown_publisher_writes_expected_markdown(tmp_path):
    article = Article(
        title="Industrial statistics",
        url="https://example.org/a",
        source="Example Source",
        summary="A useful summary.",
    )
    publication = Publication(
        proposal_id=uuid4(),
        title="BIS Newsletter",
        subtitle="Draft issue",
        sections=[
            PublicationSection(
                heading="Selected articles",
                article_ids=[article.id],
                summary="This issue contains one article.",
            )
        ],
    )
    output_path = tmp_path / "newsletter.md"

    MarkdownPublisher([article]).publish(publication, output_path)

    markdown = output_path.read_text(encoding="utf-8")
    assert "# BIS Newsletter" in markdown
    assert "Draft issue" in markdown
    assert "## Selected articles" in markdown
    assert "- **Industrial statistics**" in markdown
    assert "A useful summary." in markdown
    assert "Source: Example Source - https://example.org/a" in markdown


def test_cli_publication_create_list_show_and_publish_markdown(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    proposal_repo = SQLiteIssueProposalRepository(db_path)
    article = Article(
        title="Industrial statistics",
        url="https://example.org/a",
        source="Example Source",
        summary="A useful summary.",
    )
    article_repo.upsert(article)
    proposal = IssueProposal(
        optimiser="greedy",
        article_ids=[article.id],
        objective_value=75,
    )
    proposal_repo.insert(proposal)
    runner = CliRunner()

    create = runner.invoke(
        app,
        [
            "publication",
            "create",
            "--proposal-id",
            str(proposal.id),
            "--title",
            "BIS Newsletter",
            "--subtitle",
            "Draft issue",
            "--db",
            str(db_path),
        ],
    )
    publication_id = create.stdout.strip().split()[-1]
    list_result = runner.invoke(app, ["publication", "list", "--db", str(db_path)])
    show = runner.invoke(
        app, ["publication", "show", publication_id, "--db", str(db_path)]
    )
    output_path = tmp_path / "newsletter.md"
    publish = runner.invoke(
        app,
        [
            "publish",
            "markdown",
            "--publication-id",
            publication_id,
            "--output",
            str(output_path),
            "--db",
            str(db_path),
        ],
    )

    publication = SQLitePublicationRepository(db_path).get(publication_id)
    events = SQLiteWorkflowEventRepository(db_path).list(
        artefact_type="publication", artefact_id=publication.id if publication else None
    )
    assert create.exit_code == 0
    assert "Created publication" in create.stdout
    assert SQLitePublicationRepository(db_path).count() == 1
    assert list_result.exit_code == 0
    assert "Publications" in list_result.stdout
    assert show.exit_code == 0
    assert "Title: BIS Newsletter" in show.stdout
    assert publish.exit_code == 0
    assert "Rendered Markdown publication" in publish.stdout
    assert "# BIS Newsletter" in output_path.read_text(encoding="utf-8")
    assert [event.event_type for event in events] == [
        "publication-created",
        "publication-published",
    ]
    assert events[0].payload == {"proposal_id": str(proposal.id)}
    assert events[1].payload == {
        "format": "markdown",
        "output_path": str(output_path),
    }


def test_publication_create_requires_existing_proposal(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "publication",
            "create",
            "--proposal-id",
            str(uuid4()),
            "--title",
            "BIS Newsletter",
            "--db",
            str(tmp_path / "test.sqlite"),
        ],
    )

    assert result.exit_code == 1
    assert "Issue proposal not found" in result.stdout
