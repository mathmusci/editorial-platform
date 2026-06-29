from editorial.engine import EditorialEngine
from editorial.evaluators import RuleBasedRelevanceEvaluator
from editorial.extractors import ReadingTimeExtractor
from editorial.models import Article
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


def test_engine_runs_evaluators_over_articles_and_extractions(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    article = Article(
        title="Industrial statistics",
        url="https://example.org/a",
        summary="Forecasting uncertainty.",
    )
    article_repo.upsert(article)
    extraction_repo.insert(ReadingTimeExtractor().extract(article))
    engine = EditorialEngine(article_repo, extraction_repo, evaluation_repo)
    evaluator = RuleBasedRelevanceEvaluator(
        include=["industrial", "statistics", "forecasting"],
        exclude=["football"],
        weights={"title": 5, "summary": 2, "content": 1},
    )

    result = engine.evaluate([evaluator])

    assert result.articles == 1
    assert result.evaluators == 1
    assert result.stored == 1
    assert evaluation_repo.count() == 1
    evaluation = evaluation_repo.list(article_id=article.id)[0]
    assert evaluation.kind == "relevance"
    assert evaluation.payload["extractions"] == [
        {"kind": "reading_time", "extractor": "reading_time"}
    ]


def test_engine_evaluation_rerun_does_not_duplicate_evaluations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    article = Article(title="Industrial statistics", url="https://example.org/a")
    article_repo.upsert(article)
    engine = EditorialEngine(article_repo, extraction_repo, evaluation_repo)
    evaluator = RuleBasedRelevanceEvaluator(
        include=["industrial", "statistics"],
        exclude=[],
        weights={"title": 5},
    )

    first = engine.evaluate([evaluator])
    second = engine.evaluate([evaluator])

    assert first.stored == 1
    assert second.stored == 1
    assert evaluation_repo.count() == 1
