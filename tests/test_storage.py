from editorial.models import Article
from editorial.storage import SQLiteArticleRepository
def test_article_repository_inserts_and_skips_duplicate_url(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    article = Article(title="Example", url="https://example.org/a")
    assert repo.upsert(article) is True
    assert repo.upsert(article) is False
    assert repo.count() == 1
    assert repo.list()[0].title == "Example"
