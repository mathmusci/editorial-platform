from editorial.config import load_publication_config
from editorial.config.models import ProcessorConfig
from editorial.engine import EditorialEngine
from editorial.providers import build_provider
from editorial.providers.rss import RSSProvider
from editorial.storage import SQLiteArticleRepository


def test_rss_provider_reads_static_feed_fixture():
    provider = RSSProvider(path="fixtures/rss/sample-feed.xml", base_path="tests")

    articles = list(provider.fetch())

    assert len(articles) == 3
    assert articles[0].title == "First RSS Article"
    assert str(articles[0].url) == "https://example.org/rss/one"
    assert articles[0].source == "Example RSS Feed"
    assert articles[0].summary == "Summary for the first RSS article."
    assert articles[0].published_at.isoformat() == "2026-06-01T10:00:00+00:00"


def test_rss_provider_can_be_built_from_config_and_skips_duplicate_urls(tmp_path):
    config = ProcessorConfig(
        type="rss",
        name="Fixture RSS",
        settings={"path": "fixtures/rss/sample-feed.xml"},
    )
    provider = build_provider(config, base_path="tests")
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")

    result = EditorialEngine(repo).ingest([provider])

    assert result.fetched == 3
    assert result.added == 2
    assert result.duplicates_in_source == 1
    assert result.already_in_database == 0
    assert repo.count() == 2


def test_rss_provider_ingests_from_publication_yaml_fixture(tmp_path):
    config = load_publication_config("tests/fixtures/rss/publication.yaml")
    providers = [
        build_provider(provider_config, base_path=config.base_path)
        for provider_config in config.providers
    ]
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")

    result = EditorialEngine(repo).ingest(providers)

    assert result.fetched == 3
    assert result.added == 2
    assert result.duplicates_in_source == 1
    assert result.already_in_database == 0
