from editorial.models import Article, Extraction
from editorial.storage import SQLiteArticleRepository, SQLiteExtractionRepository


def test_extraction_repository_inserts_and_lists_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    article = Article(title="Example", url="https://example.org/a")
    article_repo.upsert(article)
    extraction = Extraction(
        article_id=article.id,
        extractor="reading_time",
        extractor_version="0.1.0",
        kind="reading_time",
        payload={"word_count": 120, "reading_minutes": 1},
    )

    extraction_repo.insert(extraction)

    assert extraction_repo.count() == 1
    stored = extraction_repo.list(article_id=article.id)[0]
    assert stored.article_id == article.id
    assert stored.extractor == "reading_time"
    assert stored.payload["word_count"] == 120


def test_extraction_repository_replaces_matching_article_extractor_and_kind(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = Article(title="Example", url="https://example.org/a")
    SQLiteArticleRepository(db_path).upsert(article)
    extraction_repo = SQLiteExtractionRepository(db_path)
    first = Extraction(
        article_id=article.id,
        extractor="reading_time",
        extractor_version="0.1.0",
        kind="reading_time",
        payload={"word_count": 120, "reading_minutes": 1},
    )
    second = Extraction(
        article_id=article.id,
        extractor="reading_time",
        extractor_version="0.1.0",
        kind="reading_time",
        payload={"word_count": 240, "reading_minutes": 2},
    )

    extraction_repo.insert(first)
    extraction_repo.insert(second)

    extractions = extraction_repo.list(article_id=article.id)
    assert len(extractions) == 1
    assert extraction_repo.count() == 1
    assert extractions[0].payload["word_count"] == 240
