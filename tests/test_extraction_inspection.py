from uuid import uuid4

import pytest
from typer.testing import CliRunner

from editorial.cli import app
from editorial.extractors import ExtractorDescriptor
from editorial.inspection import ExtractionInspectionService
from editorial.models import Article, Extraction
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)

COVERAGE_FIXTURE_CONFIG = "tests/fixtures/extraction-coverage/publication.yaml"


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
            "metadata": {"editorial_note": "Local test run"},
        },
    )
    if with_article:
        SQLiteArticleRepository(db_path).upsert(article)
    extraction_repo = SQLiteExtractionRepository(db_path)
    extraction_repo.insert(reading_time)
    extraction_repo.insert(summary)
    return article, reading_time, summary


def _store_coverage_articles(db_path) -> tuple[Article, Article]:
    complete = Article(
        title="Complete article",
        url="https://example.org/complete",
        source="Fixture Source",
    )
    missing_reading_time = Article(
        title="Missing reading time",
        url="https://example.org/missing-reading-time",
        source="Fixture Source",
    )
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(complete)
    article_repo.upsert(missing_reading_time)

    extraction_repo = SQLiteExtractionRepository(db_path)
    extraction_repo.insert(
        Extraction(
            article_id=complete.id,
            extractor="reading_time",
            extractor_version="0.1.0",
            kind="reading_time",
            payload={"reading_minutes": 4, "word_count": 700},
        )
    )
    for article, summary in [
        (complete, "Complete summary."),
        (missing_reading_time, "Summary without reading time."),
    ]:
        extraction_repo.insert(
            Extraction(
                article_id=article.id,
                extractor="llm_summary",
                extractor_version="0.1.0",
                kind="summary",
                payload={
                    "summary": summary,
                    "metadata": {
                        "generated_by": "llm",
                        "provider": "ollama",
                        "model": "qwen3.5:9b",
                        "prompt_version": "summary-v1",
                    },
                },
            )
        )
    return complete, missing_reading_time


def _coverage_descriptors() -> list[ExtractorDescriptor]:
    return [
        ExtractorDescriptor(
            key="reading_time",
            display_name="Reading time",
            kind="reading_time",
        ),
        ExtractorDescriptor(
            key="llm_summary",
            display_name="LLM summary",
            kind="summary",
        ),
    ]


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


def test_extraction_coverage_reports_present_and_missing_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _complete, missing_reading_time = _store_coverage_articles(db_path)

    report = _service(db_path).coverage(_coverage_descriptors(), missing_only=True)

    assert report.articles_selected == 2
    assert report.configured_extractors == 2
    assert report.expected_operations == 4
    assert report.present == 3
    assert report.missing == 1
    assert report.complete_articles == 1
    assert report.articles_with_missing == 1
    assert len(report.articles) == 1
    assert report.articles[0].article_id == missing_reading_time.id
    assert [item.status for item in report.articles[0].operations] == [
        "missing",
        "present",
    ]
    assert report.articles[0].operations[1].provenance == {
        "generated_by": "llm",
        "provider": "ollama",
        "model": "qwen3.5:9b",
        "prompt_version": "summary-v1",
    }


def test_extraction_coverage_can_focus_on_one_extractor(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _store_coverage_articles(db_path)

    report = _service(db_path).coverage(
        _coverage_descriptors(), extractor_keys=["reading_time"]
    )

    assert report.configured_extractors == 1
    assert report.expected_operations == 2
    assert report.present == 1
    assert report.missing == 1
    assert report.by_extractor[0].extractor == "reading_time"


def test_extraction_coverage_rejects_duplicate_extractor_keys(tmp_path):
    db_path = tmp_path / "test.sqlite"
    descriptor = _coverage_descriptors()[0]

    with pytest.raises(ValueError, match="Duplicate configured extractor keys"):
        _service(db_path).coverage([descriptor, descriptor])


def test_cli_extraction_list_discovers_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _article, reading_time, summary = _store_extractions(db_path)

    result = CliRunner().invoke(app, ["extraction", "list", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Extractions" in result.stdout
    assert str(reading_time.id) in result.stdout
    assert str(summary.id) in result.stdout


def test_cli_extraction_coverage_exposes_reading_time_gap_and_provenance(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _complete, missing_reading_time = _store_coverage_articles(db_path)

    result = CliRunner().invoke(
        app,
        [
            "extraction",
            "coverage",
            "--config",
            COVERAGE_FIXTURE_CONFIG,
            "--db",
            str(db_path),
            "--missing-only",
        ],
    )

    assert result.exit_code == 0
    assert "Extraction Coverage" in result.stdout
    assert "Coverage by Extractor" in result.stdout
    assert "Articles with missing" in result.stdout
    assert str(missing_reading_time.id) in result.stdout
    assert "Missing reading time" in result.stdout
    assert "reading_time" in result.stdout
    assert "missing" in result.stdout
    assert "llm_summary" in result.stdout
    assert "present" in result.stdout
    assert "Summary without" in result.stdout
    assert "ollama" in result.stdout
    assert "qwen3.5:9b" in result.stdout


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
    assert "Reading minutes" in result.stdout
    assert '{"reading_minutes"' not in result.stdout


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
    assert "Reading minutes" in result.stdout
    assert "Word count" in result.stdout
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
    assert "Generated by" in result.stdout
    assert "fake-summary-model" in result.stdout
    assert "summary-v1" in result.stdout
    assert "Metadata" in result.stdout
    assert "Editorial note" in result.stdout
    assert "Local test run" in result.stdout
    assert result.stdout.count("fake-summary-model") == 1


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
