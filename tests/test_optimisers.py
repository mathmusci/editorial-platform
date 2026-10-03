from editorial.config.models import OptimisationConfig
from editorial.models import Article, Evaluation, Extraction
from editorial.optimisers import (
    GreedyOptimiser,
    MilpOptimiser,
    build_optimiser,
    build_optimiser_from_request,
)
from editorial.models import OptimisationRequest


def test_build_greedy_optimiser_from_config():
    optimiser = build_optimiser(
        OptimisationConfig(
            strategy="greedy",
            settings={"max_articles": 3, "relevance_target_score": 25},
        )
    )

    assert isinstance(optimiser, GreedyOptimiser)
    assert optimiser.max_articles == 3
    assert optimiser.relevance_target_score == 25


def test_build_milp_optimiser_from_config_and_request():
    settings = {"max_articles": 3, "reading_time_target_minutes": 30}
    optimiser = build_optimiser(OptimisationConfig(strategy="milp", settings=settings))
    from_request = build_optimiser_from_request(
        OptimisationRequest(strategy="milp", settings=settings)
    )

    assert isinstance(optimiser, MilpOptimiser)
    assert isinstance(from_request, MilpOptimiser)
    assert optimiser.max_articles == from_request.max_articles == 3


def test_milp_finds_better_combination_than_greedy():
    articles = [
        Article(title=title, url=f"https://example.org/{title}")
        for title in ("a", "b", "c")
    ]
    evaluations = [
        Evaluation(
            article_id=article.id, evaluator="relevance", kind="relevance", score=score
        )
        for article, score in zip(articles, (10, 9, 9))
    ]
    extractions = [
        Extraction(
            article_id=article.id,
            extractor="reading_time",
            kind="reading_time",
            payload={"reading_minutes": minutes},
        )
        for article, minutes in zip(articles, (10, 5, 5))
    ]
    settings = {"max_articles": 2, "reading_time_target_minutes": 10}

    greedy = GreedyOptimiser(**settings).optimise(articles, extractions, evaluations)
    exact = MilpOptimiser(**settings).optimise(articles, extractions, evaluations)

    assert greedy.article_ids == [articles[0].id]
    assert exact.article_ids == [articles[1].id, articles[2].id]
    assert greedy.objective_value == 10
    assert exact.objective_value == 18
    assert exact.metadata["solver_status"] == "optimal"


def test_milp_uses_relevance_terms_and_source_penalty():
    articles = [
        Article(title="Statistics", url="https://example.org/a", source="A"),
        Article(title="Industry", url="https://example.org/b", source="A"),
        Article(title="General", url="https://example.org/c", source="B"),
    ]
    evaluations = [
        Evaluation(
            article_id=article.id, evaluator="relevance", kind="relevance", score=score
        )
        for article, score in zip(articles, (10, 10, 8))
    ]
    optimiser = MilpOptimiser(
        max_articles=2,
        relevance_target_score=10,
        mandatory_terms=["statistics", "industry"],
        mandatory_terms_weight=5,
        source_diversity_max_per_source=1,
        source_diversity_weight=3,
    )

    proposal = optimiser.optimise(articles, [], evaluations)

    assert proposal.article_ids == [articles[0].id, articles[1].id]
    assert proposal.objective_value == 27
    source_result = next(
        item
        for item in proposal.constraint_results
        if item.name == "source_diversity_max_per_source"
    )
    assert source_result.penalty == 3


def test_milp_hard_relevance_filter_and_empty_candidates():
    article = Article(title="Low score", url="https://example.org/low")
    evaluation = Evaluation(
        article_id=article.id, evaluator="relevance", kind="relevance", score=5
    )
    optimiser = MilpOptimiser(
        hard_minimum_relevance_score=10,
        reading_time_target_minutes=20,
    )

    proposal = optimiser.optimise([article], [], [evaluation])

    assert proposal.article_ids == []
    assert proposal.metadata["candidate_count"] == 0
    assert proposal.objective_value == -60


def test_milp_rejects_negative_penalty_weights():
    import pytest

    with pytest.raises(ValueError, match="reading_time_weight"):
        MilpOptimiser(reading_time_weight=-1)


def test_milp_does_not_return_partial_solver_result(monkeypatch):
    from types import SimpleNamespace

    import pytest

    monkeypatch.setattr(
        "editorial.optimisers.milp.milp",
        lambda *args, **kwargs: SimpleNamespace(
            status=1, x=[1], message="time limit reached"
        ),
    )
    article = Article(title="Candidate", url="https://example.org/a")
    evaluation = Evaluation(
        article_id=article.id, evaluator="relevance", kind="relevance", score=10
    )

    with pytest.raises(RuntimeError, match="did not find an optimal solution"):
        MilpOptimiser().optimise([article], [], [evaluation])


def test_greedy_optimiser_selects_relevant_articles():
    articles = [
        Article(title="Industrial statistics", url="https://example.org/a"),
        Article(title="Football rumours", url="https://example.org/b"),
    ]
    evaluations = [
        Evaluation(
            article_id=articles[0].id,
            evaluator="rule_relevance",
            kind="relevance",
            score=80,
        ),
        Evaluation(
            article_id=articles[1].id,
            evaluator="rule_relevance",
            kind="relevance",
            score=10,
        ),
    ]
    optimiser = GreedyOptimiser(max_articles=2, hard_minimum_relevance_score=40)

    proposal = optimiser.optimise(articles, [], evaluations)

    assert proposal.article_ids == [articles[0].id]
    assert proposal.objective_value == 80


def test_greedy_optimiser_can_select_article_below_relevance_target():
    articles = [
        Article(title="Industrial statistics", url="https://example.org/a"),
        Article(title="Weak candidate", url="https://example.org/b"),
    ]
    evaluations = [
        Evaluation(
            article_id=articles[0].id,
            evaluator="rule_relevance",
            kind="relevance",
            score=30,
        ),
        Evaluation(
            article_id=articles[1].id,
            evaluator="rule_relevance",
            kind="relevance",
            score=5,
        ),
    ]
    optimiser = GreedyOptimiser(max_articles=1, relevance_target_score=40)

    proposal = optimiser.optimise(articles, [], evaluations)

    relevance_target = next(
        result
        for result in proposal.constraint_results
        if result.name == "relevance_target_score"
    )
    assert proposal.article_ids == [articles[0].id]
    assert proposal.objective_value == 20
    assert relevance_target.kind == "goal"
    assert relevance_target.satisfied is False
    assert relevance_target.penalty == 10


def test_greedy_optimiser_treats_reading_time_target_as_soft_goal():
    article = Article(title="Industrial statistics", url="https://example.org/a")
    evaluation = Evaluation(
        article_id=article.id, evaluator="rule_relevance", kind="relevance", score=80
    )
    extraction = Extraction(
        article_id=article.id,
        extractor="reading_time",
        kind="reading_time",
        payload={"reading_minutes": 5},
    )
    optimiser = GreedyOptimiser(
        max_articles=1,
        relevance_target_score=40,
        reading_time_target_minutes=20,
        reading_time_weight=3,
    )

    proposal = optimiser.optimise([article], [extraction], [evaluation])

    reading_time = next(
        result
        for result in proposal.constraint_results
        if result.name == "reading_time_target_minutes"
    )
    assert proposal.article_ids == [article.id]
    assert reading_time.kind == "goal"
    assert reading_time.satisfied is False
    assert reading_time.penalty == 45


def test_greedy_optimiser_applies_source_diversity_penalty():
    articles = [
        Article(title="Statistics one", url="https://example.org/a", source="Same"),
        Article(title="Statistics two", url="https://example.org/b", source="Same"),
    ]
    evaluations = [
        Evaluation(
            article_id=article.id,
            evaluator="rule_relevance",
            kind="relevance",
            score=80,
        )
        for article in articles
    ]
    optimiser = GreedyOptimiser(
        max_articles=2,
        relevance_target_score=40,
        source_diversity_max_per_source=1,
        source_diversity_weight=10,
    )

    proposal = optimiser.optimise(articles, [], evaluations)

    source_diversity = next(
        result
        for result in proposal.constraint_results
        if result.name == "source_diversity_max_per_source"
    )
    assert proposal.article_ids == [article.id for article in articles]
    assert source_diversity.satisfied is False
    assert source_diversity.penalty == 10
