from editorial.engine import EditorialEngine
from editorial.models import Article, Evaluation, Extraction
from editorial.optimisers import GreedyOptimiser
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
)


def test_engine_runs_optimiser_and_stores_issue_proposal(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    proposal_repo = SQLiteIssueProposalRepository(db_path)
    article = Article(title="Industrial statistics", url="https://example.org/a")
    article_repo.upsert(article)
    extraction_repo.insert(
        Extraction(
            article_id=article.id,
            extractor="reading_time",
            kind="reading_time",
            payload={"reading_minutes": 4},
        )
    )
    evaluation_repo.insert(
        Evaluation(
            article_id=article.id,
            evaluator="rule_relevance",
            kind="relevance",
            score=75,
        )
    )
    engine = EditorialEngine(
        article_repo, extraction_repo, evaluation_repo, proposal_repo
    )

    result = engine.optimise(GreedyOptimiser(max_articles=1, relevance_target_score=40))

    assert result.optimiser == "greedy"
    assert result.selected_articles == 1
    assert proposal_repo.count() == 1


def test_engine_optimisation_rerun_creates_new_issue_proposals(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article_repo = SQLiteArticleRepository(db_path)
    extraction_repo = SQLiteExtractionRepository(db_path)
    evaluation_repo = SQLiteEvaluationRepository(db_path)
    proposal_repo = SQLiteIssueProposalRepository(db_path)
    article = Article(title="Industrial statistics", url="https://example.org/a")
    article_repo.upsert(article)
    evaluation_repo.insert(
        Evaluation(
            article_id=article.id,
            evaluator="rule_relevance",
            kind="relevance",
            score=75,
        )
    )
    engine = EditorialEngine(
        article_repo, extraction_repo, evaluation_repo, proposal_repo
    )

    engine.optimise(GreedyOptimiser(max_articles=1, relevance_target_score=40))
    engine.optimise(GreedyOptimiser(max_articles=1, relevance_target_score=40))

    assert proposal_repo.count() == 2
