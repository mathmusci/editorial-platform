from editorial.engine import EditorialEngine
from editorial.providers.static import StaticProvider
from editorial.storage import SQLiteArticleRepository
def test_engine_ingests_from_provider(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    provider = StaticProvider([{"title": "One", "url": "https://example.org/one"}, {"title": "Two", "url": "https://example.org/two"}])
    result = EditorialEngine(repo).ingest([provider])
    assert result.fetched == 2
    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert repo.count() == 2
