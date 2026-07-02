from editorial.engine import EditorialEngine
from editorial.providers.static import StaticProvider
from editorial.storage import SQLiteArticleRepository


def test_engine_ingests_from_provider(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    provider = StaticProvider(
        [
            {"title": "One", "url": "https://example.org/one"},
            {"title": "Two", "url": "https://example.org/two"},
        ]
    )
    result = EditorialEngine(repo).ingest([provider])
    assert result.fetched == 2
    assert result.added == 2
    assert result.duplicates_in_source == 0
    assert result.already_in_database == 0
    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert repo.count() == 2


def test_engine_distinguishes_source_duplicates_from_repository_duplicates(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    provider = StaticProvider(
        [
            {"title": "One", "url": "https://example.org/one"},
            {"title": "One again", "url": "https://example.org/one"},
            {"title": "Two", "url": "https://example.org/two"},
        ]
    )
    engine = EditorialEngine(repo)

    first = engine.ingest([provider])
    second = engine.ingest([provider])

    assert first.fetched == 3
    assert first.added == 2
    assert first.duplicates_in_source == 1
    assert first.already_in_database == 0
    assert (
        first.fetched
        == first.added + first.duplicates_in_source + first.already_in_database
    )

    assert second.fetched == 3
    assert second.added == 0
    assert second.duplicates_in_source == 1
    assert second.already_in_database == 2
    assert (
        second.fetched
        == second.added + second.duplicates_in_source + second.already_in_database
    )
    assert repo.count() == 2


def test_engine_reports_mixed_new_source_duplicate_and_existing_articles(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    existing_provider = StaticProvider(
        [{"title": "Existing", "url": "https://example.org/existing"}]
    )
    mixed_provider = StaticProvider(
        [
            {"title": "Existing again", "url": "https://example.org/existing"},
            {"title": "New", "url": "https://example.org/new"},
            {"title": "New duplicate", "url": "https://example.org/new"},
        ]
    )
    engine = EditorialEngine(repo)
    engine.ingest([existing_provider])

    result = engine.ingest([mixed_provider])

    assert result.fetched == 3
    assert result.added == 1
    assert result.duplicates_in_source == 1
    assert result.already_in_database == 1
    assert (
        result.fetched
        == result.added + result.duplicates_in_source + result.already_in_database
    )
    assert repo.count() == 2
