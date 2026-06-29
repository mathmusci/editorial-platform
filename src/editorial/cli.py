from __future__ import annotations
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.evaluators import build_evaluator
from editorial.extractors import build_extractor
from editorial.models import EditorialStatus
from editorial.optimisers import build_optimiser
from editorial.providers import build_provider
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
)

app = typer.Typer(help="Editorial processing platform CLI")
console = Console()


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
