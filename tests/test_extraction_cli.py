from typer.testing import CliRunner

from editorial.cli import app
from editorial.storage import SQLiteExtractionRepository


def test_cli_extract_uses_configured_reading_time_extractor(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()

    ingest_result = runner.invoke(
        app,
        ["ingest", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )
    extract_result = runner.invoke(
        app,
        ["extract", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )

    assert ingest_result.exit_code == 0
    assert extract_result.exit_code == 0
    assert "Stored extractions: 2" in extract_result.stdout
    assert SQLiteExtractionRepository(db_path).count() == 2
