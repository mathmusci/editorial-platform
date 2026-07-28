from editorial.models import Article
from editorial.storage import ArticleInsertOutcome, SQLiteArticleRepository


def test_article_repository_inserts_and_skips_duplicate_url(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    article = Article(title="Example", url="https://example.org/a")
    assert repo.insert(article) is ArticleInsertOutcome.INSERTED
    assert repo.insert(article) is ArticleInsertOutcome.ALREADY_EXISTS
    assert repo.count() == 1
    assert repo.list()[0].title == "Example"


def test_article_repository_reports_duplicate_url_for_a_different_article(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    first = Article(title="First", url="https://example.org/a")
    duplicate = Article(title="Duplicate", url="https://example.org/a")

    assert repo.insert(first) is ArticleInsertOutcome.INSERTED
    assert repo.insert(duplicate) is ArticleInsertOutcome.ALREADY_EXISTS
    assert repo.count() == 1


def test_article_repository_reports_duplicate_id_without_a_url(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    article = Article(title="Example")
    duplicate = Article(id=article.id, title="Duplicate")

    assert repo.insert(article) is ArticleInsertOutcome.INSERTED
    assert repo.insert(duplicate) is ArticleInsertOutcome.ALREADY_EXISTS
    assert repo.count() == 1


def test_article_repository_upsert_preserves_boolean_compatibility(tmp_path):
    repo = SQLiteArticleRepository(tmp_path / "test.sqlite")
    article = Article(title="Example", url="https://example.org/a")

    assert repo.upsert(article) is True
    assert repo.upsert(article) is False
