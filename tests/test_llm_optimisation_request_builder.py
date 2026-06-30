import json

import pytest

from editorial.llm import FakeLLMProvider
from editorial.prompts import (
    OPTIMISATION_REQUEST_PROMPT_VERSION,
    build_optimisation_request_prompt,
)
from editorial.request_builders import LLMOptimisationRequestBuilder
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteWorkflowEventRepository,
)


VALID_RESPONSE = (
    '{"strategy": "greedy", '
    '"settings": {"max_articles": 5}, '
    '"constraints": {"minimum_relevance": 40}, '
    '"goals": {"maximise": ["relevance"]}, '
    '"preferences": {"tone": "concise"}, '
    '"metadata": {"source": "editorial intent"}}'
)


def test_optimisation_request_prompt_contains_publication_and_instruction():
    prompt = build_optimisation_request_prompt(
        publication="BIS Newsletter",
        editor_instruction="Prioritise industrial statistics and keep it short.",
    )

    assert prompt.messages[0].role == "system"
    assert "structured optimisation request JSON" in prompt.messages[0].content
    assert prompt.messages[1].role == "user"
    assert "BIS Newsletter" in prompt.messages[1].content
    assert "Prioritise industrial statistics and keep it short." in (
        prompt.messages[1].content
    )
    assert "strategy" in prompt.messages[1].content
    assert "settings" in prompt.messages[1].content
    assert "constraints" in prompt.messages[1].content
    assert prompt.metadata == {"prompt_version": OPTIMISATION_REQUEST_PROMPT_VERSION}


def test_llm_optimisation_request_builder_valid_response_creates_request():
    provider = FakeLLMProvider(response_text=VALID_RESPONSE, model="fake-request-model")
    builder = LLMOptimisationRequestBuilder(provider)

    request = builder.build(
        publication="BIS Newsletter",
        editor_instruction="Prioritise industrial statistics and keep it short.",
        created_by="Andy",
    )

    assert provider.prompts == [
        build_optimisation_request_prompt(
            "BIS Newsletter",
            "Prioritise industrial statistics and keep it short.",
        )
    ]
    assert request.publication == "BIS Newsletter"
    assert request.strategy == "greedy"
    assert request.settings == {"max_articles": 5}
    assert request.constraints == {"minimum_relevance": 40}
    assert request.goals == {"maximise": ["relevance"]}
    assert request.preferences == {"tone": "concise"}
    assert request.created_by == "Andy"


def test_llm_optimisation_request_builder_populates_ai_provenance_metadata():
    provider = FakeLLMProvider(response_text=VALID_RESPONSE, model="fake-request-model")
    builder = LLMOptimisationRequestBuilder(provider)

    request = builder.build(
        publication=None,
        editor_instruction="Find concise industrial statistics stories.",
    )

    assert request.metadata == {
        "source": "editorial intent",
        "generated_by": "llm",
        "provider": "fake",
        "model": "fake-request-model",
        "prompt_version": OPTIMISATION_REQUEST_PROMPT_VERSION,
        "source_instruction": "Find concise industrial statistics stories.",
    }


def test_llm_optimisation_request_builder_rejects_invalid_json():
    builder = LLMOptimisationRequestBuilder(FakeLLMProvider(response_text="not json"))

    with pytest.raises(ValueError, match="valid JSON"):
        builder.build("BIS Newsletter", "Make a good issue.")


@pytest.mark.parametrize(
    "response",
    [
        '{"strategy": "", "settings": {}, "constraints": {}, "goals": {}, "preferences": {}, "metadata": {}}',
        '{"strategy": 123, "settings": {}, "constraints": {}, "goals": {}, "preferences": {}, "metadata": {}}',
    ],
)
def test_llm_optimisation_request_builder_rejects_invalid_strategy(response):
    builder = LLMOptimisationRequestBuilder(FakeLLMProvider(response_text=response))

    with pytest.raises(ValueError, match="strategy"):
        builder.build("BIS Newsletter", "Make a good issue.")


@pytest.mark.parametrize(
    "field",
    ["settings", "constraints", "goals", "preferences", "metadata"],
)
def test_llm_optimisation_request_builder_rejects_non_object_fields(field):
    payload = {
        "strategy": "greedy",
        "settings": {},
        "constraints": {},
        "goals": {},
        "preferences": {},
        "metadata": {},
    }
    payload[field] = []
    response = json.dumps(payload)
    builder = LLMOptimisationRequestBuilder(FakeLLMProvider(response_text=response))

    with pytest.raises(ValueError, match=field):
        builder.build("BIS Newsletter", "Make a good issue.")


def test_llm_optimisation_request_builder_has_no_repository_or_workflow_side_effects(
    tmp_path,
):
    db_path = tmp_path / "test.sqlite"
    builder = LLMOptimisationRequestBuilder(
        FakeLLMProvider(response_text=VALID_RESPONSE)
    )

    builder.build("BIS Newsletter", "Make a good issue.")

    assert SQLiteOptimisationRequestRepository(db_path).count() == 0
    assert SQLiteIssueProposalRepository(db_path).count() == 0
    assert SQLiteWorkflowEventRepository(db_path).count() == 0
