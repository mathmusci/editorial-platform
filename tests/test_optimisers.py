from editorial.config.models import OptimisationConfig
from editorial.models import Article, Evaluation, Extraction
from editorial.optimisers import GreedyOptimiser, build_optimiser


def test_build_greedy_optimiser_from_config():
    optimiser = build_optimiser(
        OptimisationConfig(
            strategy="greedy",
            settings={"max_articles": 3, "minimum_relevance_score": 25},
        )
    )

    assert isinstance(optimiser, GreedyOptimiser)
    assert optimiser.max_articles == 3
    assert optimiser.minimum_relevance_score == 25


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
    optimiser = GreedyOptimiser(max_articles=2, minimum_relevance_score=40)

    proposal = optimiser.optimise(articles, [], evaluations)

    assert proposal.article_ids == [articles[0].id]
    assert proposal.objective_value == 80


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
        minimum_relevance_score=40,
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
        minimum_relevance_score=40,
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
