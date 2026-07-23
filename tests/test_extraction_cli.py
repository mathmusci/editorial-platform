from typer.testing import CliRunner

import editorial.cli as cli
from editorial.cli import app
from editorial.models import Article, Extraction
from editorial.storage import SQLiteArticleRepository
from editorial.storage import SQLiteExtractionRepository

BIS_FIXTURE_CONFIG = "tests/fixtures/bis/publication.yaml"


def test_cli_extract_uses_configured_reading_time_extractor(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()

    ingest_result = runner.invoke(
        app,
        ["ingest", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )
    extract_result = runner.invoke(
        app,
        ["extract", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    assert ingest_result.exit_code == 0
    assert extract_result.exit_code == 0
    assert "Stored extractions: 2" in extract_result.stdout
    assert "Operations: 2" in extract_result.stdout
    assert SQLiteExtractionRepository(db_path).count() == 2


def test_cli_extract_no_progress_uses_stable_line_output(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    runner.invoke(app, ["ingest", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)])

    result = runner.invoke(
        app,
        [
            "extract",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "Publication: BIS Newsletter" in result.stdout
    assert "Operations: 2" in result.stdout
    assert "Stored extractions: 2" in result.stdout
    assert "Failed: 0" in result.stdout


def test_cli_extract_forced_progress_renders_rich_progress(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    runner.invoke(app, ["ingest", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)])

    result = runner.invoke(
        app,
        [
            "extract",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--progress",
        ],
    )

    assert result.exit_code == 0
    assert "Extracting evidence" in result.stdout
    assert "Article:" in result.stdout
    assert "Extractor: Reading time" in result.stdout
    assert "2/2" in result.stdout
    assert "Stored: 2" in result.stdout


class OllamaMetadataExtractor:
    name = "llm_summary"
    version = "0.1.0"
    display_name = "Local summary"

    def __init__(self):
        self.provider = type("Provider", (), {"name": "ollama", "model": "llama3.2"})()

    def extract(self, article):
        return Extraction(
            article_id=article.id,
            extractor=self.name,
            extractor_version=self.version,
            kind="summary",
            payload={"summary": "Local summary"},
        )


def test_cli_extract_progress_displays_ollama_provider_and_model(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite"
    config_path = tmp_path / "publication.yaml"
    config_path.write_text(
        """
publication:
  name: Local LLM Test
extractors:
  - type: llm_summary
    name: Local summary
    provider:
      type: ollama
      model: llama3.2
""",
        encoding="utf-8",
    )
    SQLiteArticleRepository(db_path).upsert(Article(title="Slow local inference"))
    monkeypatch.setattr(
        cli, "build_extractor", lambda config: OllamaMetadataExtractor()
    )

    result = CliRunner().invoke(
        app,
        ["extract", "--config", str(config_path), "--db", str(db_path), "--progress"],
    )

    assert result.exit_code == 0
    assert "Provider: ollama" in result.stdout
    assert "Model: llama3.2" in result.stdout
    assert "Extractor: Local summary" in result.stdout
