from editorial.engine import EditorialEngine
from editorial.evaluators import RuleBasedRelevanceEvaluator
from editorial.extractors import ReadingTimeExtractor
from datetime import UTC, datetime

import pytest

from editorial.models import Article, Evaluation
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


class CountingEvaluator:
    name = "counting"
    version = "0.1.0"

    def __init__(self):
        self.calls = []

    def evaluate(self, article, extractions):
        self.calls.append(article.title)
        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="relevance",
            score=50,
        )


class FailingEvaluator:
    name = "failing"
    version = "0.1.0"

    def evaluate(self, article, extractions):
        raise RuntimeError(f"cannot evaluate {article.title}")


class ProviderBackedEvaluator(CountingEvaluator):
    name = "provider_backed"

    def __init__(self):
        super().__init__()
        self.provider = type("Provider", (), {"name": "ollama", "model": "llama3.2"})()


def _article(title: str, day: int) -> Article:
    created_at = datetime(2026, 1, day, tzinfo=UTC)
    return Article(title=title, created_at=created_at, updated_at=created_at)


def _engine(db_path):
    return EditorialEngine(
        SQLiteArticleRepository(db_path),
        SQLiteExtractionRepository(db_path),
        SQLiteEvaluationRepository(db_path),
    )


def test_engine_evaluate_emits_progress_with_provider_metadata(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(Article(title="One"))
    events = []

    result = _engine(db_path).evaluate(
        [ProviderBackedEvaluator()], progress=events.append
    )

    assert result.operations == 1
    assert [event.outcome for event in events] == ["started", "stored"]
    assert events[-1].completed == 1
    assert events[-1].stored == 1
    assert events[-1].provider == "ollama"
    assert events[-1].model == "llama3.2"


def test_engine_evaluate_limit_and_offset_select_deterministic_subset(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(_article("Oldest", 1))
    article_repo.upsert(_article("Middle", 2))
    article_repo.upsert(_article("Newest", 3))
    evaluator = CountingEvaluator()

    result = _engine(db_path).evaluate([evaluator], limit=1, offset=1)

    assert result.articles == 1
    assert result.operations == 1
    assert evaluator.calls == ["Middle"]


def test_engine_evaluate_article_ids_restrict_selection(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    first = _article("First", 1)
    second = _article("Second", 2)
    article_repo.upsert(first)
    article_repo.upsert(second)
    evaluator = CountingEvaluator()

    result = _engine(db_path).evaluate([evaluator], article_ids=[first.id])

    assert result.articles == 1
    assert evaluator.calls == ["First"]


def test_engine_evaluate_reports_missing_article_id(tmp_path):
    db_path = tmp_path / "test.sqlite"
    missing_id = _article("Missing", 1).id

    with pytest.raises(ValueError, match="Article not found for evaluation"):
        _engine(db_path).evaluate([CountingEvaluator()], article_ids=[missing_id])


def test_engine_evaluate_missing_only_skips_existing_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(_article("Only", 1))
    engine = _engine(db_path)
    engine.evaluate([CountingEvaluator()])
    evaluator = CountingEvaluator()
    events = []

    result = engine.evaluate([evaluator], missing_only=True, progress=events.append)

    assert result.stored == 0
    assert result.skipped == 1
    assert result.failed == 0
    assert evaluator.calls == []
    assert [event.outcome for event in events] == ["started", "skipped"]


def test_engine_evaluate_force_reprocesses_existing_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    article_repo.upsert(_article("Only", 1))
    engine = _engine(db_path)
    engine.evaluate([CountingEvaluator()])
    evaluator = CountingEvaluator()

    result = engine.evaluate([evaluator], force=True)

    assert result.stored == 1
    assert result.skipped == 0
    assert evaluator.calls == ["Only"]
    assert SQLiteEvaluationRepository(db_path).count() == 1


def test_engine_evaluate_rejects_missing_only_with_force(tmp_path):
    db_path = tmp_path / "test.sqlite"

    with pytest.raises(ValueError, match="missing_only and force"):
        _engine(db_path).evaluate([CountingEvaluator()], missing_only=True, force=True)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"limit": 0}, "limit must be a positive integer"),
        ({"offset": -1}, "offset must be zero or greater"),
    ],
)
def test_engine_evaluate_rejects_invalid_selection_options(tmp_path, options, message):
    with pytest.raises(ValueError, match=message):
        _engine(tmp_path / "test.sqlite").evaluate([CountingEvaluator()], **options)


def test_engine_evaluate_emits_failed_progress_before_reraising(tmp_path):
    db_path = tmp_path / "test.sqlite"
    SQLiteArticleRepository(db_path).upsert(Article(title="One"))
    events = []

    with pytest.raises(RuntimeError, match="cannot evaluate One"):
        _engine(db_path).evaluate([FailingEvaluator()], progress=events.append)

    assert [event.outcome for event in events] == ["started", "failed"]
    assert events[-1].completed == 1
    assert events[-1].failed == 1
