from editorial.models import ConstraintResult, IssueProposal


def test_constraint_result_model_validation():
    result = ConstraintResult(
        name="reading_time_target_minutes",
        kind="goal",
        satisfied=False,
        value=12,
        target=20,
        penalty=24,
        message="Below target.",
    )

    assert result.kind == "goal"
    assert result.penalty == 24


def test_issue_proposal_model_validation():
    proposal = IssueProposal(
        optimiser="greedy",
        optimiser_version="0.1.0",
        objective_value=42,
        constraint_results=[
            ConstraintResult(
                name="max_articles",
                kind="hard",
                satisfied=True,
                value=2,
                target=8,
            )
        ],
        metadata={"candidate_count": 3},
    )

    assert proposal.optimiser == "greedy"
    assert proposal.article_ids == []
    assert proposal.constraint_results[0].name == "max_articles"
