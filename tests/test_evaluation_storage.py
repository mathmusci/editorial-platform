from editorial.models import Article, Evaluation
from editorial.storage import SQLiteArticleRepository, SQLiteEvaluationRepository


def test_evaluation_repository_inserts_and_lists_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = Article(title="Industrial statistics", url="https://example.org/a")
    SQLiteArticleRepository(db_path).upsert(article)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    evaluation = Evaluation(
        article_id=article.id,
        evaluator="rule_relevance",
        evaluator_version="0.1.0",
        kind="relevance",
        criterion="relevance",
        score=80,
        confidence=1.0,
        rationale="Matched include terms.",
        payload={"matched_include_terms": ["industrial", "statistics"]},
    )

    evaluation_repo.insert(evaluation)

    assert evaluation_repo.count() == 1
    stored = evaluation_repo.list(article_id=article.id)[0]
    assert stored.article_id == article.id
    assert stored.evaluator == "rule_relevance"
    assert stored.kind == "relevance"
    assert stored.score == 80


def test_evaluation_repository_replaces_matching_article_evaluator_and_kind(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = Article(title="Industrial statistics", url="https://example.org/a")
    SQLiteArticleRepository(db_path).upsert(article)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    first = Evaluation(
        article_id=article.id,
        evaluator="rule_relevance",
        kind="relevance",
        score=20,
        confidence=1.0,
        payload={"matched_include_terms": ["industrial"]},
    )
    second = Evaluation(
        article_id=article.id,
        evaluator="rule_relevance",
        kind="relevance",
        score=70,
        confidence=1.0,
        payload={"matched_include_terms": ["industrial", "statistics"]},
    )

    evaluation_repo.insert(first)
    evaluation_repo.insert(second)

    evaluations = evaluation_repo.list(article_id=article.id)
    assert len(evaluations) == 1
    assert evaluation_repo.count() == 1
    assert evaluations[0].score == 70
