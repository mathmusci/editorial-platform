from uuid import uuid4

from typer.testing import CliRunner

from editorial.cli import app
from editorial.inspection import ExtractionInspectionService
from editorial.models import Article, Extraction
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)


def _service(db_path) -> ExtractionInspectionService:
    return ExtractionInspectionService(
        extractions=SQLiteExtractionRepository(db_path),
        articles=SQLiteArticleRepository(db_path),
        workflow_events=SQLiteWorkflowEventRepository(db_path),
    )


def _store_extractions(
    db_path,
    *,
    with_article: bool = True,
) -> tuple[Article, Extraction, Extraction]:
    article = Article(
        title="Industrial statistics",
        url="https://example.org/industrial-statistics",
        source="Fixture Source",
    )
    reading_time = Extraction(
        article_id=article.id,
        extractor="reading_time",
        extractor_version="0.1.0",
        kind="reading_time",
        payload={"reading_minutes": 4, "word_count": 700},
    )
    summary = Extraction(
        article_id=article.id,
        extractor="summary",
        extractor_version="0.1.0",
        kind="summary",
        payload={
            "summary": "A concise industrial statistics summary.",
            "generated_by": "llm",
            "provider": "fake",
            "model": "fake-summary-model",
            "prompt_version": "summary-v1",
        },
    )
    if with_article:
        SQLiteArticleRepository(db_path).upsert(article)
    extraction_repo = SQLiteExtractionRepository(db_path)
    extraction_repo.insert(reading_time)
    extraction_repo.insert(summary)
    return article, reading_time, summary


def test_extraction_inspection_service_builds_review_model(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article, reading_time, _summary = _store_extractions(db_path)

    inspection = _service(db_path).get(reading_time.id)

    assert inspection is not None
    assert inspection.extraction == reading_time
    assert inspection.article == article
    assert inspection.payload_highlights == {
        "reading_minutes": 4,
        "word_count": 700,
    }


def test_cli_extraction_list_discovers_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, reading_time, summary = _store_extractions(db_path)

    result = CliRunner().invoke(app, ["extraction", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Extractions" in result.stdout
    assert str(reading_time.id) in result.stdout
    assert str(summary.id) in result.stdout


def test_cli_extraction_list_displays_article_and_payload_preview(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, _reading_time, _summary = _store_extractions(db_path)

    result = CliRunner().invoke(app, ["extraction", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "https://example.org/industrial-" in result.stdout
    assert "statistics" in result.stdout
    assert "reading_time" in result.stdout
    assert "summary" in result.stdout
    assert "reading_minutes" in result.stdout


def test_cli_extraction_show_displays_identity_and_article_details(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article, reading_time, _summary = _store_extractions(db_path)

    result = CliRunner().invoke(
        app, ["extraction", "show", str(reading_time.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(reading_time.id) in result.stdout
    assert "Extraction" in result.stdout
    assert str(article.id) in result.stdout
    assert "Industrial statistics" in result.stdout
    assert "Fixture Source" in result.stdout
    assert "https://example.org/industrial-statistics" in result.stdout


def test_cli_extraction_show_displays_reading_time_payload_highlights(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, reading_time, _summary = _store_extractions(db_path)

    result = CliRunner().invoke(
        app, ["extraction", "show", str(reading_time.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "Payload Highlights" in result.stdout
    assert "reading_minutes" in result.stdout
    assert "word_count" in result.stdout
    assert "700" in result.stdout


def test_cli_extraction_show_displays_summary_payload_highlights(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, _reading_time, summary = _store_extractions(db_path)

    result = CliRunner().invoke(
        app, ["extraction", "show", str(summary.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "A concise industrial statistics summary." in result.stdout
    assert "Provenance" in result.stdout
    assert "generated_by" in result.stdout
    assert "fake-summary-model" in result.stdout
    assert "summary-v1" in result.stdout


def test_cli_extraction_show_handles_missing_article_gracefully(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, reading_time, _summary = _store_extractions(db_path, with_article=False)

    result = CliRunner().invoke(
        app, ["extraction", "show", str(reading_time.id), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert str(reading_time.article_id) in result.stdout
    assert "not available" in result.stdout


def test_cli_extraction_show_invalid_id_gives_clear_error(tmp_path):
    db_path = tmp_path / "test.sqlite"
    extraction_id = uuid4()

    result = CliRunner().invoke(
        app, ["extraction", "show", str(extraction_id), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert f"Extraction not found: {extraction_id}" in result.stdout
