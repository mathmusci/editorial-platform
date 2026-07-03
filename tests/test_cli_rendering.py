from editorial.cli import _format_details, _format_structured_value


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
