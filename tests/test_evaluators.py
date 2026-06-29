from editorial.config.models import ProcessorConfig
from editorial.evaluators import RuleBasedRelevanceEvaluator, build_evaluator
from editorial.models import Article, Extraction


def test_rule_based_relevance_evaluator_scores_terms_without_mutating_inputs():
    article = Article(
        title="Industrial statistics and forecasting",
        summary="Data uncertainty for business decisions.",
        content="Celebrity football gossip.",
    )
    extraction = Extraction(
        article_id=article.id,
        extractor="reading_time",
        kind="reading_time",
        payload={"reading_minutes": 1},
    )
    original_article = article.model_dump()
    original_extraction = extraction.model_dump()
    evaluator = RuleBasedRelevanceEvaluator(
        include=["statistics", "forecasting", "data", "business"],
        exclude=["football", "celebrity"],
        weights={"title": 5, "summary": 2, "content": 1},
    )

    evaluation = evaluator.evaluate(article, [extraction])

    assert article.model_dump() == original_article
    assert extraction.model_dump() == original_extraction
    assert evaluation.article_id == article.id
    assert evaluation.evaluator == "rule_relevance"
    assert evaluation.kind == "relevance"
    assert evaluation.score == 37.5
    assert evaluation.confidence == 1.0
    assert evaluation.payload["matched_include_terms"] == [
        "business",
        "data",
        "forecasting",
        "statistics",
    ]
    assert evaluation.payload["matched_exclude_terms"] == ["celebrity", "football"]
    assert evaluation.payload["extractions"] == [
        {"kind": "reading_time", "extractor": "reading_time"}
    ]


def test_build_rule_based_relevance_evaluator_from_config():
    config = ProcessorConfig(
        type="rule_relevance",
        settings={
            "include": ["statistics"],
            "exclude": ["football"],
            "weights": {"title": 10},
        },
    )

    evaluator = build_evaluator(config)

    assert isinstance(evaluator, RuleBasedRelevanceEvaluator)
    assert evaluator.include == ["statistics"]
    assert evaluator.exclude == ["football"]
    assert evaluator.weights["title"] == 10
