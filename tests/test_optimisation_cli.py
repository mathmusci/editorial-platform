from pathlib import Path

import yaml
from typer.testing import CliRunner

from editorial.cli import app
from editorial.storage import SQLiteIssueProposalRepository

BIS_FIXTURE_CONFIG = "tests/fixtures/bis/publication.yaml"


def test_cli_optimise_stores_append_only_issue_proposals(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()

    assert (
        runner.invoke(
            app,
            [
                "ingest",
                "--config",
                BIS_FIXTURE_CONFIG,
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
                BIS_FIXTURE_CONFIG,
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
                BIS_FIXTURE_CONFIG,
                "--db",
                str(db_path),
            ],
        ).exit_code
        == 0
    )
    first = runner.invoke(
        app,
        ["optimise", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )
    second = runner.invoke(
        app,
        ["optimise", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Optimiser: greedy" in first.stdout
    assert SQLiteIssueProposalRepository(db_path).count() == 2

    milp_config = yaml.safe_load(Path(BIS_FIXTURE_CONFIG).read_text())
    milp_config["optimisation"]["strategy"] = "milp"
    milp_config_path = tmp_path / "publication-milp.yaml"
    milp_config_path.write_text(yaml.safe_dump(milp_config))
    exact = runner.invoke(
        app,
        ["optimise", "--config", str(milp_config_path), "--db", str(db_path)],
    )

    assert exact.exit_code == 0, exact.output
    assert "Optimiser: milp" in exact.stdout
    assert SQLiteIssueProposalRepository(db_path).count() == 3
