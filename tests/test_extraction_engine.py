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
    assert events[-1].skipped == 0
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
    assert result.skipped == 0
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
    assert events[-1].skipped == 0
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
