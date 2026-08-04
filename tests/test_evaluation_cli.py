import re

from typer.testing import CliRunner

import editorial.cli as cli
from editorial.cli import app
from editorial.models import Evaluation
from editorial.storage import SQLiteArticleRepository, SQLiteEvaluationRepository

BIS_FIXTURE_CONFIG = "tests/fixtures/bis/publication.yaml"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _unstyled(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def test_cli_evaluate_uses_configured_rule_based_evaluator_idempotently(tmp_path):
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
    first_evaluate = runner.invoke(
        app,
        ["evaluate", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )
    second_evaluate = runner.invoke(
        app,
        ["evaluate", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    assert ingest_result.exit_code == 0
    assert extract_result.exit_code == 0
    assert first_evaluate.exit_code == 0
    assert second_evaluate.exit_code == 0
    assert "Stored evaluations: 2" in first_evaluate.stdout
    assert "Stored evaluations: 2" in second_evaluate.stdout
    assert "Operations: 2" in first_evaluate.stdout
    assert "Skipped: 0" in first_evaluate.stdout
    assert "Failed: 0" in first_evaluate.stdout
    assert SQLiteEvaluationRepository(db_path).count() == 2


def _prepare_database(runner, db_path):
    runner.invoke(app, ["ingest", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)])
    runner.invoke(
        app, ["extract", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)]
    )


def test_cli_evaluate_limit_reports_selected_subset_totals(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--limit",
            "1",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "Articles: 1" in result.stdout
    assert "Operations: 1" in result.stdout
    assert "Stored evaluations: 1" in result.stdout
    assert SQLiteEvaluationRepository(db_path).count() == 1


def test_cli_evaluate_offset_selects_later_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)
    expected_article = SQLiteArticleRepository(db_path).list()[1]

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--offset",
            "1",
            "--limit",
            "1",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    evaluations = SQLiteEvaluationRepository(db_path).list()
    assert len(evaluations) == 1
    assert evaluations[0].article_id == expected_article.id


def test_cli_evaluate_article_id_selects_single_article(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)
    article = SQLiteArticleRepository(db_path).list()[0]

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--article-id",
            str(article.id),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    evaluations = SQLiteEvaluationRepository(db_path).list()
    assert len(evaluations) == 1
    assert evaluations[0].article_id == article.id


def test_cli_evaluate_missing_only_skips_existing_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)
    runner.invoke(
        app,
        ["evaluate", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--missing-only",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "Operations: 2" in result.stdout
    assert "Stored evaluations: 0" in result.stdout
    assert "Skipped: 2" in result.stdout
    assert SQLiteEvaluationRepository(db_path).count() == 2


def test_cli_evaluate_force_reprocesses_existing_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)
    runner.invoke(
        app,
        ["evaluate", "--config", BIS_FIXTURE_CONFIG, "--db", str(db_path)],
    )

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--force",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "Stored evaluations: 2" in result.stdout
    assert "Skipped: 0" in result.stdout
    assert SQLiteEvaluationRepository(db_path).count() == 2


class OllamaMetadataEvaluator:
    name = "llm_relevance"
    version = "0.1.0"
    display_name = "Local relevance"

    def __init__(self):
        self.provider = type("Provider", (), {"name": "ollama", "model": "llama3.2"})()

    def evaluate(self, article, extractions):
        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="relevance",
            score=80,
        )


def test_cli_evaluate_progress_displays_provider_model_and_evaluator(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "test.sqlite"
    runner = CliRunner()
    _prepare_database(runner, db_path)
    monkeypatch.setattr(
        cli, "build_evaluator", lambda config: OllamaMetadataEvaluator()
    )

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--limit",
            "1",
            "--progress",
        ],
    )

    assert result.exit_code == 0
    assert "Evaluating articles" in result.stdout
    assert "Evaluator: Local relevance" in result.stdout
    assert "Provider: ollama" in result.stdout
    assert "Model: llama3.2" in result.stdout
    assert "1/1" in result.stdout


def test_cli_evaluate_rejects_non_positive_limit(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(tmp_path / "test.sqlite"),
            "--limit",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "--limit must be a positive integer" in _unstyled(result.output)


def test_cli_evaluate_rejects_negative_offset(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(tmp_path / "test.sqlite"),
            "--offset",
            "-1",
        ],
    )

    assert result.exit_code != 0
    assert "--offset must be zero or greater" in _unstyled(result.output)


def test_cli_evaluate_rejects_missing_only_with_force(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            "--config",
            BIS_FIXTURE_CONFIG,
            "--db",
            str(tmp_path / "test.sqlite"),
            "--missing-only",
            "--force",
        ],
    )

    assert result.exit_code != 0
    assert "--missing-only and --force cannot be used together" in _unstyled(
        result.output
    )
