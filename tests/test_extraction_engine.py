from editorial.engine import EditorialEngine
from editorial.extractors import ReadingTimeExtractor
from editorial.models import Article
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
