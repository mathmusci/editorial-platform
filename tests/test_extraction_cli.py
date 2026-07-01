from typer.testing import CliRunner

from editorial.cli import app
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
    assert SQLiteExtractionRepository(db_path).count() == 2
