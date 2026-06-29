from editorial.models import Article, ConstraintResult, IssueProposal
from editorial.storage import SQLiteArticleRepository, SQLiteIssueProposalRepository


def test_issue_proposal_repository_insert_list_get_and_count(tmp_path):
    db_path = tmp_path / "test.sqlite"
    article = Article(title="Industrial statistics", url="https://example.org/a")
    SQLiteArticleRepository(db_path).upsert(article)
    repo = SQLiteIssueProposalRepository(db_path)
    proposal = IssueProposal(
        optimiser="greedy",
        optimiser_version="0.1.0",
        article_ids=[article.id],
        objective_value=88.5,
        constraint_results=[
            ConstraintResult(
                name="relevance_target_score",
                kind="goal",
                satisfied=True,
                value=80,
                target=40,
            )
        ],
        metadata={"candidate_count": 1},
    )

    repo.insert(proposal)

    assert repo.count() == 1
    listed = repo.list()[0]
    fetched = repo.get(proposal.id)
    assert listed.id == proposal.id
    assert fetched is not None
    assert fetched.article_ids == [article.id]
    assert fetched.constraint_results[0].name == "relevance_target_score"


def test_issue_proposal_repository_is_append_only(tmp_path):
    repo = SQLiteIssueProposalRepository(tmp_path / "test.sqlite")

    repo.insert(IssueProposal(optimiser="greedy", objective_value=1))
    repo.insert(IssueProposal(optimiser="greedy", objective_value=1))

    assert repo.count() == 2
