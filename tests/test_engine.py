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
