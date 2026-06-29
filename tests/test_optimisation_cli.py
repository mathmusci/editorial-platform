from typer.testing import CliRunner

from editorial.cli import app
from editorial.storage import SQLiteIssueProposalRepository


def test_cli_optimise_stores_append_only_issue_proposals(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()

    assert (
        runner.invoke(
            app,
            [
                "ingest",
                "--config",
                "examples/bis/publication.yaml",
                "--db",
                str(db_path),
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "extract",
                "--config",
                "examples/bis/publication.yaml",
                "--db",
                str(db_path),
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "evaluate",
                "--config",
                "examples/bis/publication.yaml",
                "--db",
                str(db_path),
            ],
        ).exit_code
        == 0
    )
    first = runner.invoke(
        app,
        ["optimise", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )
    second = runner.invoke(
        app,
        ["optimise", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Optimiser: greedy" in first.stdout
    assert SQLiteIssueProposalRepository(db_path).count() == 2
