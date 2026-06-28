from __future__ import annotations
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.models import EditorialStatus
from editorial.providers import build_provider
from editorial.storage import SQLiteArticleRepository
app = typer.Typer(help="Editorial processing platform CLI"); console = Console()
@app.command()
def ingest(config: Path = typer.Option(..., "--config", "-c"), db: Path = typer.Option(Path("editorial.sqlite"), "--db")) -> None:
    cfg = load_publication_config(config); providers = [build_provider(p, base_path=cfg.base_path) for p in cfg.providers if p.enabled]
    result = EditorialEngine(SQLiteArticleRepository(db)).ingest(providers)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Fetched: {result.fetched}"); console.print(f"Inserted: {result.inserted}"); console.print(f"Skipped duplicates: {result.skipped_duplicates}")
@app.command("list")
def list_articles(db: Path = typer.Option(Path("editorial.sqlite"), "--db"), status: EditorialStatus | None = typer.Option(None, "--status"), limit: int | None = typer.Option(None, "--limit")) -> None:
    articles = SQLiteArticleRepository(db).list(status=status, limit=limit)
    table = Table(title="Articles"); table.add_column("Status"); table.add_column("Source"); table.add_column("Title"); table.add_column("URL")
    for a in articles: table.add_row(a.status.value, a.source or "", a.title, str(a.url) if a.url else "")
    console.print(table)
