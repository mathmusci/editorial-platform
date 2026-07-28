from datetime import UTC, datetime

import pytest

from editorial.engine import EditorialEngine
from editorial.extractors import ReadingTimeExtractor
from editorial.models import Article, Extraction
from editorial.storage import SQLiteArticleRepository, SQLiteExtractionRepository


def test_engine_runs_extractors_over_stored_articles(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(
        Article(title="One", url="https://example.org/one", summary="One two three.")
    )
    article_repo.upsert(
        Article(title="Two", url="https://example.org/two", summary="Four five six.")
    )
    engine = EditorialEngine(article_repo, extraction_repo)

    result = engine.extract([ReadingTimeExtractor(words_per_minute=2)])

    assert result.articles == 2
    assert result.extractors == 1
    assert result.stored == 2
    assert extraction_repo.count() == 2
    assert {extraction.kind for extraction in extraction_repo.list()} == {
        "reading_time"
    }


def test_engine_extraction_rerun_does_not_duplicate_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(
        Article(title="One", url="https://example.org/one", summary="One two three.")
    )
    engine = EditorialEngine(article_repo, extraction_repo)

    first = engine.extract([ReadingTimeExtractor(words_per_minute=2)])
    second = engine.extract([ReadingTimeExtractor(words_per_minute=2)])

    assert first.stored == 1
    assert second.stored == 1
    assert extraction_repo.count() == 1


class RecordingExtractor:
    name = "recording"
    version = "0.1.0"

    def extract(self, article):
        return Extraction(
            article_id=article.id,
            extractor=self.name,
            extractor_version=self.version,
            kind="recording",
            payload={"title": article.title},
        )


class FailingExtractor:
    name = "failing"
    version = "0.1.0"

    def extract(self, article):
        raise RuntimeError(f"cannot extract {article.title}")


class ProviderBackedExtractor(RecordingExtractor):
    name = "provider_backed"

    def __init__(self):
        self.provider = type("Provider", (), {"name": "ollama", "model": "llama3.2"})()


class CountingExtractor(RecordingExtractor):
    name = "counting"

    def __init__(self):
        self.calls = []

    def extract(self, article):
        self.calls.append(article.title)
        return super().extract(article)


def _article(title: str, day: int) -> Article:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return Article(title=title, created_at=created_at, updated_at=created_at)


def test_engine_extract_emits_progress_events_with_total_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(Article(title="One"))
    article_repo.upsert(Article(title="Two"))
    events = []

    result = EditorialEngine(article_repo, extraction_repo).extract(
        [RecordingExtractor(), ReadingTimeExtractor()], progress=events.append
    )

    assert result.operations == 4
    assert {event.total for event in events} == {4}
    assert [event.outcome for event in events].count("started") == 4
    assert [event.outcome for event in events].count("stored") == 4
    assert events[-1].completed == 4
    assert events[-1].stored == 4
    assert events[-1].failed == 0


def test_engine_extract_progress_callback_is_optional(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(Article(title="One"))

    result = EditorialEngine(article_repo, extraction_repo).extract(
        [RecordingExtractor()]
    )

    assert result.stored == 1
    assert result.failed == 0
    assert extraction_repo.count() == 1


def test_engine_extract_emits_failed_progress_event_before_reraising(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(Article(title="One"))
    events = []

    with pytest.raises(RuntimeError, match="cannot extract One"):
        EditorialEngine(article_repo, extraction_repo).extract(
            [FailingExtractor()], progress=events.append
        )

    assert [event.outcome for event in events] == ["started", "failed"]
    assert events[-1].completed == 1
    assert events[-1].stored == 0
    assert events[-1].failed == 1
    assert extraction_repo.count() == 0


def test_engine_extract_progress_includes_provider_model_metadata(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(Article(title="One"))
    events = []

    EditorialEngine(article_repo, extraction_repo).extract(
        [ProviderBackedExtractor()], progress=events.append
    )

    assert events[0].provider == "ollama"
    assert events[0].model == "llama3.2"


def test_engine_extract_progress_omits_provider_model_for_deterministic_extractor(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(Article(title="One"))
    events = []

    EditorialEngine(article_repo, extraction_repo).extract(
        [ReadingTimeExtractor()], progress=events.append
    )

    assert events[0].provider is None
    assert events[0].model is None


def test_engine_extract_limit_and_offset_select_deterministic_subset(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(_article("Oldest", 1))
    article_repo.upsert(_article("Middle", 2))
    article_repo.upsert(_article("Newest", 3))
    extractor = CountingExtractor()

    result = EditorialEngine(article_repo, extraction_repo).extract(
        [extractor], limit=1, offset=1
    )

    assert result.articles == 1
    assert result.operations == 1
    assert result.stored == 1
    assert extractor.calls == ["Middle"]


def test_engine_extract_article_ids_restrict_selection(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    first = _article("First", 1)
    second = _article("Second", 2)
    article_repo.upsert(first)
    article_repo.upsert(second)
    extractor = CountingExtractor()

    result = EditorialEngine(article_repo, extraction_repo).extract(
        [extractor], article_ids=[first.id]
    )

    assert result.articles == 1
    assert extractor.calls == ["First"]


def test_engine_extract_article_ids_report_missing_id(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    missing_id = _article("Missing", 1).id

    with pytest.raises(ValueError, match="Article not found"):
        EditorialEngine(article_repo, extraction_repo).extract(
            [RecordingExtractor()], article_ids=[missing_id]
        )


def test_engine_extract_missing_only_skips_existing_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(_article("Only", 1))
    engine = EditorialEngine(article_repo, extraction_repo)
    first_extractor = CountingExtractor()
    second_extractor = CountingExtractor()
    events = []

    first = engine.extract([first_extractor])
    second = engine.extract(
        [second_extractor], missing_only=True, progress=events.append
    )

    assert first.stored == 1
    assert first.skipped == 0
    assert second.stored == 0
    assert second.skipped == 1
    assert second.failed == 0
    assert second_extractor.calls == []
    assert [event.outcome for event in events] == ["started", "skipped"]
    assert events[-1].completed == 1
    assert events[-1].stored == 0
    assert events[-1].skipped == 1


def test_engine_extract_force_reprocesses_existing_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article_repo.upsert(_article("Only", 1))
    engine = EditorialEngine(article_repo, extraction_repo)
    engine.extract([CountingExtractor()])
    extractor = CountingExtractor()

    result = engine.extract([extractor], force=True)

    assert result.stored == 1
    assert result.skipped == 0
    assert extractor.calls == ["Only"]


def test_engine_extract_rejects_missing_only_with_force(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)

    with pytest.raises(ValueError, match="missing_only and force"):
        EditorialEngine(article_repo, extraction_repo).extract(
            [RecordingExtractor()], missing_only=True, force=True
        )
