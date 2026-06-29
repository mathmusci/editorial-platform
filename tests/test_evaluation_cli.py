from typer.testing import CliRunner

from editorial.cli import app
from editorial.storage import SQLiteEvaluationRepository


def test_cli_evaluate_uses_configured_rule_based_evaluator_idempotently(tmp_path):
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
    first_evaluate = runner.invoke(
        app,
        ["evaluate", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )
    second_evaluate = runner.invoke(
        app,
        ["evaluate", "--config", "examples/bis/publication.yaml", "--db", str(db_path)],
    )

    assert ingest_result.exit_code == 0
    assert extract_result.exit_code == 0
    assert first_evaluate.exit_code == 0
    assert second_evaluate.exit_code == 0
    assert "Stored evaluations: 2" in first_evaluate.stdout
    assert "Stored evaluations: 2" in second_evaluate.stdout
    assert SQLiteEvaluationRepository(db_path).count() == 2
