from uuid import uuid4

import pytest

from editorial.llm import FakeLLMProvider
from editorial.models import ReviewDecision
from editorial.prompts import REVIEW_PROMPT_VERSION, build_review_prompt
from editorial.reviewers import LLMReviewAssistant
from editorial.storage import SQLiteWorkflowEventRepository


def test_review_prompt_contains_artefact_context():
    artefact_id = uuid4()
    context = "Proposal includes five articles and exceeds reading-time target."

    prompt = build_review_prompt("issue_proposal", artefact_id, context)

    assert prompt.messages[0].role == "system"
    assert "human editors make final decisions" in prompt.messages[0].content
    assert prompt.messages[1].role == "user"
    assert "issue_proposal" in prompt.messages[1].content
    assert str(artefact_id) in prompt.messages[1].content
    assert context in prompt.messages[1].content
    assert "decision" in prompt.messages[1].content
    assert "findings" in prompt.messages[1].content
    assert "recommendations" in prompt.messages[1].content
    assert prompt.metadata == {"prompt_version": REVIEW_PROMPT_VERSION}


def test_llm_review_assistant_valid_response_creates_review():
    artefact_id = uuid4()
    context = "Proposal includes five articles and exceeds reading-time target."
    provider = FakeLLMProvider(
        response_text=(
            '{"decision": "needs_changes", '
            '"comments": "Reading time is too long.", '
            '"findings": {"reading_time": "above target"}, '
            '"recommendations": {"remove_articles": 1}}'
        ),
        model="fake-review-model",
    )
    assistant = LLMReviewAssistant(provider)

    review = assistant.recommend("issue_proposal", artefact_id, context)

    assert provider.prompts == [
        build_review_prompt("issue_proposal", artefact_id, context)
    ]
    assert review.artefact_type == "issue_proposal"
    assert review.artefact_id == artefact_id
    assert review.reviewer == "llm_review_assistant"
    assert review.decision == ReviewDecision.NEEDS_CHANGES
    assert review.comments == "Reading time is too long."
    assert review.findings == {"reading_time": "above target"}
    assert review.recommendations == {"remove_articles": 1}


def test_llm_review_assistant_populates_ai_provenance_metadata():
    provider = FakeLLMProvider(
        response_text=(
            '{"decision": "comment", "comments": "Looks reasonable.", '
            '"findings": {}, "recommendations": {}}'
        ),
        model="fake-review-model",
    )

    review = LLMReviewAssistant(provider).recommend(
        "publication", uuid4(), "Markdown draft context"
    )

    assert review.metadata == {
        "generated_by": "llm",
        "provider": "fake",
        "model": "fake-review-model",
        "prompt_version": REVIEW_PROMPT_VERSION,
    }


def test_llm_review_assistant_rejects_invalid_json():
    assistant = LLMReviewAssistant(FakeLLMProvider(response_text="not json"))

    with pytest.raises(ValueError, match="valid JSON"):
        assistant.recommend("issue_proposal", uuid4(), "context")


def test_llm_review_assistant_rejects_invalid_decision():
    assistant = LLMReviewAssistant(
        FakeLLMProvider(
            response_text=(
                '{"decision": "defer", "comments": "No.", '
                '"findings": {}, "recommendations": {}}'
            )
        )
    )

    with pytest.raises(ValueError, match="decision"):
        assistant.recommend("issue_proposal", uuid4(), "context")


@pytest.mark.parametrize(
    "response",
    [
        '{"decision": "comment", "comments": "No findings.", "findings": [], "recommendations": {}}',
        '{"decision": "comment", "comments": "No recommendations.", "findings": {}, "recommendations": []}',
    ],
)
def test_llm_review_assistant_rejects_non_object_findings_or_recommendations(response):
    assistant = LLMReviewAssistant(FakeLLMProvider(response_text=response))

    with pytest.raises(ValueError):
        assistant.recommend("issue_proposal", uuid4(), "context")


def test_llm_review_assistant_does_not_create_workflow_event(tmp_path):
    db_path = tmp_path / "test.sqlite"
    provider = FakeLLMProvider(
        response_text=(
            '{"decision": "approve", "comments": "Ready.", '
            '"findings": {}, "recommendations": {}}'
        )
    )

    LLMReviewAssistant(provider).recommend("issue_proposal", uuid4(), "context")

    assert SQLiteWorkflowEventRepository(db_path).count() == 0
