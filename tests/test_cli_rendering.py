from editorial.cli import (
    _format_details,
    _format_structured_value,
    _split_provenance,
    _split_rendered_payload,
)


def test_format_structured_value_renders_mapping_without_json_quotes():
    rendered = _format_structured_value({"Arxiv - Computer Science": 1})

    assert rendered == "Arxiv - Computer Science: 1"
    assert '{"' not in rendered


def test_format_structured_value_renders_numbers_without_quotes():
    assert _format_structured_value(19.64) == "19.64"


def test_format_structured_value_renders_lists_as_bullets():
    rendered = _format_structured_value(["approve", "request_changes"])

    assert "- approve" in rendered
    assert "- request_changes" in rendered
    assert "[" not in rendered


def test_format_details_renders_nested_values_readably():
    rendered = _format_details(
        "Publication metrics",
        {"article_count": 1, "evaluation_count": 1106},
    )

    assert "Publication metrics:" in rendered
    assert "Article count: 1" in rendered
    assert "Evaluation count: 1106" in rendered


def test_split_provenance_keeps_additional_metadata_separate():
    provenance, additional = _split_provenance(
        {
            "provider": "ollama",
            "model": "qwen3.5:9b",
            "editorial_note": "Local test run",
        }
    )

    assert provenance == {"provider": "ollama", "model": "qwen3.5:9b"}
    assert additional == {"editorial_note": "Local test run"}


def test_split_rendered_payload_removes_only_already_presented_fields():
    payload, metadata = _split_rendered_payload(
        {
            "summary": "A summary.",
            "quality": "reviewed",
            "metadata": {
                "provider": "ollama",
                "model": "qwen3.5:9b",
                "editorial_note": "Local test run",
            },
        },
        {"summary": "A summary."},
        {"provider": "ollama", "model": "qwen3.5:9b"},
    )

    assert payload == {"quality": "reviewed"}
    assert metadata == {"editorial_note": "Local test run"}
