from typer.testing import CliRunner

from editorial.cli import app

RSS_FIXTURE_CONFIG = "tests/fixtures/rss/publication.yaml"


def test_cli_ingest_reports_added_source_duplicates_and_database_duplicates(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["ingest", "--config", RSS_FIXTURE_CONFIG, "--db", str(db_path)],
    )
    second = runner.invoke(
        app,
        ["ingest", "--config", RSS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    assert first.exit_code == 0
    assert "Fetched: 3" in first.stdout
    assert "Added: 2" in first.stdout
    assert "Duplicates in source: 1" in first.stdout
    assert "Already in database: 0" in first.stdout
    assert "Skipped duplicates" not in first.stdout

    assert second.exit_code == 0
    assert "Fetched: 3" in second.stdout
    assert "Added: 0" in second.stdout
    assert "Duplicates in source: 1" in second.stdout
    assert "Already in database: 2" in second.stdout
    assert "Skipped duplicates" not in second.stdout
