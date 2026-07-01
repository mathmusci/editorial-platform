from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from editorial.cli_helpers import (
    parse_key_values,
    parse_payload,
    record_publication_created,
    record_publication_rendered,
    record_review_submitted,
    request_from_config,
    run_optimisation_request,
)
from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.evaluators import build_evaluator
from editorial.extractors import build_extractor
from editorial.inspection import ProposalInspection, ProposalInspectionService
from editorial.models import (
    EditorialStatus,
    Review,
    ReviewDecision,
    WorkflowEvent,
)
from editorial.publishing import MarkdownPublisher, PublicationBuilder
from editorial.providers import build_provider
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
from editorial.workflow import WorkflowProjection

app = typer.Typer(help="Editorial processing platform CLI")
workflow_app = typer.Typer(help="Record and inspect workflow events")
optimisation_request_app = typer.Typer(help="Create and run optimisation requests")
review_app = typer.Typer(help="Create and inspect editorial reviews")
publication_app = typer.Typer(help="Create and inspect publication artefacts")
publish_app = typer.Typer(help="Render publications to output formats")
proposal_app = typer.Typer(help="Inspect issue proposals")
app.add_typer(workflow_app, name="workflow")
app.add_typer(optimisation_request_app, name="optimisation-request")
app.add_typer(review_app, name="review")
app.add_typer(publication_app, name="publication")
app.add_typer(publish_app, name="publish")
app.add_typer(proposal_app, name="proposal")
console = Console()


def _proposal_inspection_service(db: Path) -> ProposalInspectionService:
    return ProposalInspectionService(
        proposals=SQLiteIssueProposalRepository(db),
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        evaluations=SQLiteEvaluationRepository(db),
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
        reviews=SQLiteReviewRepository(db),
        publications=SQLitePublicationRepository(db),
    )


def _format_optional(value: object | None) -> str:
    return "" if value is None else str(value)


@app.command()
def ingest(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    providers = [
        build_provider(p, base_path=cfg.base_path) for p in cfg.providers if p.enabled
    ]
    result = EditorialEngine(SQLiteArticleRepository(db)).ingest(providers)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Fetched: {result.fetched}")
    console.print(f"Inserted: {result.inserted}")
    console.print(f"Skipped duplicates: {result.skipped_duplicates}")


@app.command()
def extract(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    extractors = [build_extractor(e) for e in cfg.extractors if e.enabled]
    result = EditorialEngine(
        SQLiteArticleRepository(db), SQLiteExtractionRepository(db)
    ).extract(extractors)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Articles: {result.articles}")
    console.print(f"Extractors: {result.extractors}")
    console.print(f"Stored extractions: {result.stored}")


@app.command()
def evaluate(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    evaluators = [build_evaluator(e) for e in cfg.evaluators if e.enabled]
    result = EditorialEngine(
        SQLiteArticleRepository(db),
        SQLiteExtractionRepository(db),
        SQLiteEvaluationRepository(db),
    ).evaluate(evaluators)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Articles: {result.articles}")
    console.print(f"Evaluators: {result.evaluators}")
    console.print(f"Stored evaluations: {result.stored}")


@app.command()
def optimise(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    request = request_from_config(config, metadata={"source": "editorial optimise"})
    SQLiteOptimisationRequestRepository(db).insert(request)
    result, proposal = run_optimisation_request(request, db)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Optimiser: {result.optimiser}")
    console.print(f"Optimisation request: {request.id}")
    console.print(f"Selected articles: {result.selected_articles}")
    console.print(f"Objective value: {result.objective_value}")
    if proposal is not None:
        for constraint in proposal.constraint_results:
            console.print(
                f"- {constraint.name}: satisfied={constraint.satisfied}, penalty={constraint.penalty}"
            )


@app.command("list")
def list_articles(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    status: EditorialStatus | None = typer.Option(None, "--status"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    articles = SQLiteArticleRepository(db).list(status=status, limit=limit)
    table = Table(title="Articles")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("URL")
    for a in articles:
        table.add_row(
            a.status.value, a.source or "", a.title, str(a.url) if a.url else ""
        )
    console.print(table)


@proposal_app.command("list")
def proposal_list(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    proposals = _proposal_inspection_service(db).list(limit=limit)
    if not proposals:
        console.print("No proposals found.")
        return

    table = Table(title="Issue Proposals", show_lines=True)
    table.add_column("Proposal ID", no_wrap=True)
    table.add_column("Details")
    for proposal in proposals:
        status_parts = [
            f"reviews: {proposal.review_count}",
            f"publications: {proposal.publication_count}",
        ]
        request = _format_optional(proposal.optimisation_request_id)
        details = "\n".join(
            [
                f"Created: {proposal.created_at.isoformat()}",
                "Optimisation request:",
                request or "not available",
                f"Articles: {proposal.selected_article_count}",
                f"Objective: {proposal.objective_value}",
                f"Publication: {proposal.publication_name or 'not available'}",
                f"Status: {', '.join(status_parts)}",
            ]
        )
        table.add_row(
            str(proposal.proposal_id),
            details,
        )
    console.print(table)


@proposal_app.command("show")
def proposal_show(
    proposal_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _proposal_inspection_service(db).get(proposal_id)
    if inspection is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)
    _render_proposal_inspection(inspection)


def _render_proposal_inspection(inspection: ProposalInspection) -> None:
    proposal = inspection.proposal
    request_id = (
        str(inspection.optimisation_request.id)
        if inspection.optimisation_request
        else _format_optional(proposal.metadata.get("optimisation_request_id"))
    )
    summary = "\n".join(
        [
            f"[bold]Proposal:[/bold] {proposal.id}",
            f"[bold]Created:[/bold] {proposal.created_at.isoformat()}",
            f"[bold]Optimisation request:[/bold] {request_id or 'not available'}",
            f"[bold]Publication:[/bold] {inspection.publication_name or 'not available'}",
            f"[bold]Objective value:[/bold] {proposal.objective_value}",
            f"[bold]Selected articles:[/bold] {len(proposal.article_ids)}",
        ]
    )
    console.print(Panel(summary, title="Issue Proposal", expand=False))
    _render_selected_articles(inspection)
    _render_constraints(inspection)
    _render_workflow_events(inspection)
    _render_reviews(inspection)
    _render_publications(inspection)
    _render_metadata(inspection)


def _render_selected_articles(inspection: ProposalInspection) -> None:
    console.print("[bold]Selected Articles[/bold]")
    for article in inspection.selected_articles:
        reading = (
            "not available"
            if article.reading_minutes is None
            else f"{article.reading_minutes} min"
        )
        relevance = (
            "not available"
            if article.relevance_score is None
            else str(article.relevance_score)
        )
        details = "\n".join(
            [
                f"[bold]Title:[/bold] {article.title}",
                f"[bold]Source:[/bold] {article.source or 'not available'}",
                f"[bold]URL:[/bold] {article.url or 'not available'}",
                f"Reading time: {reading}",
                f"Relevance: {relevance}",
                f"Rationale: {article.relevance_rationale or 'not available'}",
            ]
        )
        console.print(Panel(details, title=str(article.article_id), expand=False))


def _render_constraints(inspection: ProposalInspection) -> None:
    if not inspection.constraint_results:
        console.print(Panel("No constraint results available.", title="Constraints"))
        return

    table = Table(title="Constraints")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Satisfied")
    table.add_column("Value")
    table.add_column("Target")
    table.add_column("Penalty")
    table.add_column("Message")
    for constraint in inspection.constraint_results:
        table.add_row(
            constraint.name,
            constraint.kind,
            str(constraint.satisfied),
            _format_optional(constraint.value),
            _format_optional(constraint.target),
            str(constraint.penalty),
            constraint.message or "",
        )
    console.print(table)


def _render_workflow_events(inspection: ProposalInspection) -> None:
    if not inspection.workflow_events:
        console.print(Panel("No workflow events found.", title="Workflow"))
        return

    table = Table(title="Workflow")
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in inspection.workflow_events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


def _render_reviews(inspection: ProposalInspection) -> None:
    if not inspection.reviews:
        console.print(Panel("No reviews found.", title="Reviews"))
        return

    table = Table(title="Reviews")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Reviewer")
    table.add_column("Decision")
    table.add_column("Comments")
    for review in inspection.reviews:
        table.add_row(
            review.created_at.isoformat(),
            str(review.id),
            review.reviewer,
            review.decision.value,
            review.comments or "",
        )
    console.print(table)


def _render_publications(inspection: ProposalInspection) -> None:
    if not inspection.publications:
        console.print(Panel("No publications found.", title="Publications"))
        return

    table = Table(title="Publications")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Title")
    table.add_column("Sections")
    for publication in inspection.publications:
        table.add_row(
            publication.created_at.isoformat(),
            str(publication.id),
            publication.title,
            str(len(publication.sections)),
        )
    console.print(table)


def _render_metadata(inspection: ProposalInspection) -> None:
    if not inspection.metadata:
        return

    table = Table(title="Metadata")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(inspection.metadata.items()):
        table.add_row(key, json.dumps(value, sort_keys=True))
    console.print(table)


@workflow_app.command("record")
def workflow_record(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    event_type: str = typer.Option(..., "--event-type"),
    actor: str | None = typer.Option(None, "--actor"),
    reason: str | None = typer.Option(None, "--reason"),
    payload: str = typer.Option("{}", "--payload"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    event = WorkflowEvent(
        artefact_type=artefact_type,
        artefact_id=artefact_id,
        event_type=event_type,
        actor=actor,
        reason=reason,
        payload=parse_payload(payload),
    )
    SQLiteWorkflowEventRepository(db).insert(event)
    console.print(f"Recorded workflow event {event.id}")


@workflow_app.command("history")
def workflow_history(
    artefact_type: str | None = typer.Option(None, "--artefact-type"),
    artefact_id: UUID | None = typer.Option(None, "--artefact-id"),
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    events = SQLiteWorkflowEventRepository(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id, limit=limit
    )
    if not events:
        console.print("No workflow events found.")
        return

    table = Table(title="Workflow Events")
    table.add_column("Created")
    table.add_column("Artefact")
    table.add_column("Event", no_wrap=True)
    table.add_column("Actor")
    table.add_column("Reason")
    for event in events:
        table.add_row(
            event.created_at.isoformat(),
            f"{event.artefact_type}:{event.artefact_id}",
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


@workflow_app.command("state")
def workflow_state(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    events = SQLiteWorkflowEventRepository(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id
    )
    state = WorkflowProjection().state_for(events)
    console.print(f"Workflow state: {state}")


@review_app.command("create")
def review_create(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    reviewer: str = typer.Option(..., "--reviewer"),
    decision: ReviewDecision = typer.Option(..., "--decision"),
    comments: str | None = typer.Option(None, "--comments"),
    finding: list[str] | None = typer.Option(None, "--finding"),
    recommendation: list[str] | None = typer.Option(None, "--recommendation"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    review = Review(
        artefact_type=artefact_type,
        artefact_id=artefact_id,
        reviewer=reviewer,
        decision=decision,
        comments=comments,
        findings=parse_key_values(finding, "--finding"),
        recommendations=parse_key_values(recommendation, "--recommendation"),
    )
    SQLiteReviewRepository(db).insert(review)
    record_review_submitted(review, db)
    console.print(f"Created review {review.id}")


@review_app.command("list")
def review_list(
    artefact_type: str | None = typer.Option(None, "--artefact-type"),
    artefact_id: UUID | None = typer.Option(None, "--artefact-id"),
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    reviews = SQLiteReviewRepository(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id, limit=limit
    )
    if not reviews:
        console.print("No reviews found.")
        return

    table = Table(title="Reviews")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Artefact")
    table.add_column("Reviewer")
    table.add_column("Decision")
    table.add_column("Comments")
    for review in reviews:
        table.add_row(
            review.created_at.isoformat(),
            str(review.id),
            f"{review.artefact_type}:{review.artefact_id}",
            review.reviewer,
            review.decision.value,
            review.comments or "",
        )
    console.print(table)


@review_app.command("show")
def review_show(
    review_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    review = SQLiteReviewRepository(db).get(review_id)
    if review is None:
        console.print(f"Review not found: {review_id}")
        raise typer.Exit(1)

    console.print(f"Review: {review.id}")
    console.print(f"Artefact: {review.artefact_type}:{review.artefact_id}")
    console.print(f"Reviewer: {review.reviewer}")
    console.print(f"Decision: {review.decision.value}")
    console.print(f"Comments: {review.comments or ''}")
    console.print(f"Created at: {review.created_at.isoformat()}")
    console.print(f"Findings: {json.dumps(review.findings, sort_keys=True)}")
    console.print(
        f"Recommendations: {json.dumps(review.recommendations, sort_keys=True)}"
    )
    console.print(f"Metadata: {json.dumps(review.metadata, sort_keys=True)}")


@publication_app.command("create")
def publication_create(
    proposal_id: UUID = typer.Option(..., "--proposal-id"),
    title: str = typer.Option(..., "--title"),
    subtitle: str | None = typer.Option(None, "--subtitle"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    proposal = SQLiteIssueProposalRepository(db).get(proposal_id)
    if proposal is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)

    publication = PublicationBuilder().build(
        proposal=proposal,
        articles=SQLiteArticleRepository(db).list(),
        extractions=SQLiteExtractionRepository(db).list(),
        evaluations=SQLiteEvaluationRepository(db).list(),
        title=title,
        subtitle=subtitle,
    )
    SQLitePublicationRepository(db).insert(publication)
    record_publication_created(publication, db)
    console.print(f"Created publication {publication.id}")


@publication_app.command("list")
def publication_list(
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    publications = SQLitePublicationRepository(db).list(limit=limit)
    if not publications:
        console.print("No publications found.")
        return

    table = Table(title="Publications")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Proposal", no_wrap=True)
    table.add_column("Title")
    table.add_column("Sections")
    for publication in publications:
        table.add_row(
            publication.created_at.isoformat(),
            str(publication.id),
            str(publication.proposal_id),
            publication.title,
            str(len(publication.sections)),
        )
    console.print(table)


@publication_app.command("show")
def publication_show(
    publication_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    publication = SQLitePublicationRepository(db).get(publication_id)
    if publication is None:
        console.print(f"Publication not found: {publication_id}")
        raise typer.Exit(1)

    console.print(f"Publication: {publication.id}")
    console.print(f"Proposal: {publication.proposal_id}")
    console.print(f"Title: {publication.title}")
    console.print(f"Subtitle: {publication.subtitle or ''}")
    console.print(f"Created at: {publication.created_at.isoformat()}")
    console.print(f"Sections: {len(publication.sections)}")
    for section in publication.sections:
        console.print(f"- {section.heading}: {len(section.article_ids)} articles")
    console.print(f"Metadata: {json.dumps(publication.metadata, sort_keys=True)}")


@publish_app.command("markdown")
def publish_markdown(
    publication_id: UUID = typer.Option(..., "--publication-id"),
    output: Path = typer.Option(..., "--output"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    publication = SQLitePublicationRepository(db).get(publication_id)
    if publication is None:
        console.print(f"Publication not found: {publication_id}")
        raise typer.Exit(1)

    MarkdownPublisher(SQLiteArticleRepository(db).list()).publish(publication, output)
    record_publication_rendered(publication, output, db)
    console.print(f"Rendered Markdown publication {publication.id} to {output}")


@optimisation_request_app.command("create")
def optimisation_request_create(
    config: Path = typer.Option(..., "--config", "-c"),
    created_by: str | None = typer.Option(None, "--created-by"),
    parent_request_id: UUID | None = typer.Option(None, "--parent-request-id"),
    parent_proposal_id: UUID | None = typer.Option(None, "--parent-proposal-id"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = request_from_config(
        config,
        created_by=created_by,
        parent_request_id=parent_request_id,
        parent_proposal_id=parent_proposal_id,
        metadata={"source": "editorial optimisation-request create"},
    )
    SQLiteOptimisationRequestRepository(db).insert(request)
    console.print(f"Created optimisation request {request.id}")


@optimisation_request_app.command("list")
def optimisation_request_list(
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    requests = SQLiteOptimisationRequestRepository(db).list(limit=limit)
    if not requests:
        console.print("No optimisation requests found.")
        return

    table = Table(title="Optimisation Requests")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Publication")
    table.add_column("Strategy")
    table.add_column("Created By")
    for request in requests:
        table.add_row(
            request.created_at.isoformat(),
            str(request.id),
            request.publication or "",
            request.strategy,
            request.created_by or "",
        )
    console.print(table)


@optimisation_request_app.command("show")
def optimisation_request_show(
    request_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = SQLiteOptimisationRequestRepository(db).get(request_id)
    if request is None:
        console.print(f"Optimisation request not found: {request_id}")
        raise typer.Exit(1)

    console.print(f"Optimisation request: {request.id}")
    console.print(f"Publication: {request.publication or ''}")
    console.print(f"Strategy: {request.strategy}")
    console.print(f"Created by: {request.created_by or ''}")
    console.print(f"Created at: {request.created_at.isoformat()}")
    console.print(f"Settings: {json.dumps(request.settings, sort_keys=True)}")
    console.print(f"Constraints: {json.dumps(request.constraints, sort_keys=True)}")
    console.print(f"Goals: {json.dumps(request.goals, sort_keys=True)}")
    console.print(f"Preferences: {json.dumps(request.preferences, sort_keys=True)}")


@optimisation_request_app.command("run")
def optimisation_request_run(
    request_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = SQLiteOptimisationRequestRepository(db).get(request_id)
    if request is None:
        console.print(f"Optimisation request not found: {request_id}")
        raise typer.Exit(1)

    result, _proposal = run_optimisation_request(request, db)
    console.print(f"Created issue proposal {result.proposal_id}")
    console.print(f"Selected articles: {result.selected_articles}")
    console.print(f"Objective value: {result.objective_value}")
