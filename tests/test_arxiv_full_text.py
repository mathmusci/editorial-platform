from urllib.error import HTTPError

import pytest

from editorial.content_view import with_full_text
from editorial.engine import EditorialEngine
from editorial.evaluators.rule_relevance import RuleBasedRelevanceEvaluator
from editorial.extractors.arxiv_full_text import ArxivFullTextExtractor, arxiv_id
from editorial.extractors.factory import describe_extractor
from editorial.extractors.llm_summary import LLMSummaryExtractor
from editorial.extractors.reading_time import ReadingTimeExtractor
from editorial.llm.testing import FakeLLMProvider
from editorial.models import Article
from editorial.config.models import ProcessorConfig
from editorial.inspection.extractions import ExtractionInspectionService
from editorial.optimisers.greedy import GreedyOptimiser
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)


def _paper_html(text):
    return (
        '<html><header>Site navigation</header><div class="ltx_document">'
        "<h1>Paper title</h1><nav>Table of contents</nav>"
        f"<section><p>{text}</p></section></div><footer>Site footer</footer></html>"
    ).encode()


def test_arxiv_html_full_text_and_safe_article_identification(monkeypatch):
    article = Article(title="Paper", url="https://arxiv.org/abs/2402.08954v1")
    requested = []

    def download(url):
        requested.append(url)
        return _paper_html("Full paper evidence " * 30)

    monkeypatch.setattr("editorial.extractors.arxiv_full_text._download", download)
    extraction = ArxivFullTextExtractor().extract(article)

    assert arxiv_id(article) == "2402.08954v1"
    assert requested == ["https://arxiv.org/html/2402.08954v1"]
    assert extraction.payload["format"] == "html"
    assert "Full paper evidence" in extraction.payload["content"]
    assert "Site navigation" not in extraction.payload["content"]
    assert "Table of contents" not in extraction.payload["content"]
    assert (
        arxiv_id(Article(title="Other", url="https://example.org/abs/2402.08954"))
        is None
    )
    assert (
        arxiv_id(Article(title="Invalid", url="https://arxiv.org/abs/../../etc"))
        is None
    )


def test_arxiv_pdf_fallback_when_html_is_unavailable(monkeypatch):
    article = Article(title="Paper", url="https://arxiv.org/abs/2402.08954")
    requested = []

    def download(url):
        requested.append(url)
        if "/html/" in url:
            raise HTTPError(url, 404, "Not found", {}, None)
        return b"%PDF-1.4 fake fixture"

    class Reader:
        def __init__(self, stream):
            assert stream.read().startswith(b"%PDF")
            self.pages = [
                type(
                    "Page",
                    (),
                    {"extract_text": lambda self: "PDF paper evidence " * 30},
                )()
            ]

    monkeypatch.setattr("editorial.extractors.arxiv_full_text._download", download)
    monkeypatch.setattr("editorial.extractors.arxiv_full_text.PdfReader", Reader)
    extraction = ArxivFullTextExtractor().extract(article)

    assert requested == [
        "https://arxiv.org/html/2402.08954",
        "https://arxiv.org/pdf/2402.08954",
    ]
    assert extraction.payload["format"] == "pdf"
    assert "PDF paper evidence" in extraction.payload["content"]


def test_full_text_drives_subsequent_processing_of_existing_article(
    tmp_path, monkeypatch
):
    db = tmp_path / "editorial.sqlite"
    articles = SQLiteArticleRepository(db)
    extractions = SQLiteExtractionRepository(db)
    evaluations = SQLiteEvaluationRepository(db)
    article = Article(
        title="Statistics paper",
        url="https://arxiv.org/abs/2402.08954",
        summary="Abstract only",
    )
    other = Article(
        title="Other source", url="https://example.org/story", summary="Other abstract"
    )
    articles.insert(article)
    articles.insert(other)
    monkeypatch.setattr(
        "editorial.extractors.arxiv_full_text._download",
        lambda url: _paper_html("Industry evidence in complete body. " * 30),
    )
    engine = EditorialEngine(articles, extractions, evaluations)
    llm = FakeLLMProvider(response_text="Summary from full paper")

    result = engine.extract(
        [
            ReadingTimeExtractor(),
            LLMSummaryExtractor(llm),
            ArxivFullTextExtractor(),
        ]
    )
    stored = extractions.list(article.id)
    reading = next(item for item in stored if item.kind == "reading_time")

    assert result.skipped == 1
    assert result.stored == 5
    assert reading.payload["word_count"] > 100
    assert any(
        "Industry evidence in complete body" in prompt.messages[1].content
        for prompt in llm.prompts
    )
    assert with_full_text(article, stored).content.startswith("Paper title")
    assert articles.get(article.id).content is None
    assert (
        engine.evaluate(
            [RuleBasedRelevanceEvaluator(include=["industry"], exclude=[])]
        ).stored
        == 2
    )
    judgement = next(
        item for item in evaluations.list() if item.article_id == article.id
    )
    assert judgement.payload["matched_include_terms"] == ["industry"]
    assert GreedyOptimiser(mandatory_terms=["industry"])._candidate(
        article, stored, judgement
    ).mandatory_terms == {"industry"}
    coverage = ExtractionInspectionService(
        extractions, articles, SQLiteWorkflowEventRepository(db)
    ).coverage([describe_extractor(ProcessorConfig(type="arxiv_full_text"))])
    assert coverage.expected_operations == 1
    assert coverage.missing == 0
    assert (
        next(item for item in coverage.articles if item.article_id == other.id)
        .operations[0]
        .status
        == "not_applicable"
    )


def test_unusable_full_text_does_not_replace_abstract(monkeypatch):
    article = Article(
        title="Paper", url="https://arxiv.org/abs/2402.08954", summary="Abstract"
    )
    monkeypatch.setattr(
        "editorial.extractors.arxiv_full_text._download",
        lambda url: b"<html>Unavailable</html>" if "/html/" in url else b"%PDF",
    )
    monkeypatch.setattr(
        "editorial.extractors.arxiv_full_text.PdfReader",
        lambda stream: type("Reader", (), {"pages": []})(),
    )

    with pytest.raises(ValueError, match="No usable full text"):
        ArxivFullTextExtractor().extract(article)
    assert article.content is None
