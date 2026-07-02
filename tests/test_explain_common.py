from editorial.explain.common import (
    NextAction,
    payload_subset,
    payload_value,
    simple_payload_highlights,
)


def test_next_action_model_records_label_and_command():
    action = NextAction(label="Inspect article", command="editorial article show 1")

    assert action.label == "Inspect article"
    assert action.command == "editorial article show 1"


def test_payload_value_reads_top_level_and_metadata_values():
    payload = {
        "provider": "top-level",
        "metadata": {"model": "fixture-model"},
    }

    assert payload_value(payload, "provider") == "top-level"
    assert payload_value(payload, "model") == "fixture-model"
    assert payload_value(payload, "missing") is None


def test_payload_subset_keeps_requested_existing_keys_only():
    payload = {"reading_minutes": 4, "word_count": 700, "other": "ignored"}

    assert payload_subset(payload, ("reading_minutes", "missing")) == {
        "reading_minutes": 4
    }


def test_simple_payload_highlights_skips_nested_and_configured_keys():
    payload = {
        "metadata": {"model": "fixture"},
        "summary": "Stored summary",
        "nested": {"not": "included"},
        "score": 12,
    }

    assert simple_payload_highlights(payload, skip_keys=("metadata",)) == {
        "summary": "Stored summary",
        "score": 12,
    }
