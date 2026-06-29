from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table
from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.evaluators import build_evaluator
from editorial.extractors import build_extractor
from editorial.models import EditorialStatus, WorkflowEvent
from editorial.optimisers import build_optimiser
from editorial.providers import build_provider
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteWorkflowEventRepository,
)
from editorial.workflow import WorkflowProjection

app = typer.Typer(help="Editorial processing platform CLI")
workflow_app = typer.Typer(help="Record and inspect workflow events")
app.add_typer(workflow_app, name="workflow")
console = Console()


def _parse_payload(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("payload must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter("payload must be a JSON object")
    return parsed


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
    optimiser = build_optimiser(cfg.optimisation)
    result = EditorialEngine(
        SQLiteArticleRepository(db),
        SQLiteExtractionRepository(db),
        SQLiteEvaluationRepository(db),
        SQLiteIssueProposalRepository(db),
    ).optimise(optimiser)
    proposal = SQLiteIssueProposalRepository(db).get(result.proposal_id)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Optimiser: {result.optimiser}")
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
        payload=_parse_payload(payload),
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
