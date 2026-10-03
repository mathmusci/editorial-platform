from __future__ import annotations

import io
import re
import time
from html.parser import HTMLParser
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pypdf import PdfReader

from editorial.models import Article, Extraction

_ARXIV_ID = re.compile(
    r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.I
)
_MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
_MIN_TEXT_CHARS = 200
_REQUEST_INTERVAL_SECONDS = 3
_request_lock = Lock()
_last_request_at = 0.0
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "wbr",
}


def arxiv_id(article: Article) -> str | None:
    if article.url is None:
        return None
    url = urlsplit(str(article.url))
    if url.scheme not in {"http", "https"} or url.hostname not in {
        "arxiv.org",
        "www.arxiv.org",
        "export.arxiv.org",
    }:
        return None
    parts = url.path.lstrip("/").split("/", 1)
    if len(parts) != 2 or parts[0] not in {"abs", "html", "pdf"}:
        return None
    identifier = parts[1].removesuffix(".pdf")
    return identifier if _ARXIV_ID.fullmatch(identifier) else None


class _PaperHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if self.depth == 0 and "ltx_document" in classes:
            self.depth = 1
            return
        if not self.depth:
            return
        if tag not in _VOID_TAGS:
            self.depth += 1
        if tag in {"script", "style", "nav", "footer"}:
            self.ignored += 1
        if tag in {"p", "div", "section", "h1", "h2", "h3", "h4", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in _VOID_TAGS:
            if tag in {"script", "style", "nav", "footer"} and self.ignored:
                self.ignored -= 1
            self.depth -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.depth and not self.ignored:
            self.parts.append(" " + data)

    def text(self) -> str:
        return "\n".join(
            line
            for line in (
                " ".join(part.split()) for part in "".join(self.parts).splitlines()
            )
            if line
        )


def _download(url: str) -> bytes:
    global _last_request_at
    request = Request(
        url, headers={"User-Agent": "editorial-platform/1.0 (full-text research)"}
    )
    with _request_lock:
        time.sleep(
            max(0, _REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at))
        )
        _last_request_at = time.monotonic()
        with urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > _MAX_DOWNLOAD_BYTES:
                raise ValueError(f"arXiv document exceeds download limit: {url}")
            data = response.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValueError(f"arXiv document exceeds download limit: {url}")
    return data


class ArxivFullTextExtractor:
    name = "arxiv_full_text"
    version = "0.1.0"
    kind = "full_text"

    def applies_to(self, article: Article) -> bool:
        return arxiv_id(article) is not None

    def extract(self, article: Article) -> Extraction:
        identifier = arxiv_id(article)
        if identifier is None:
            raise ValueError("arXiv full text requires an arxiv.org article URL")
        html_url = f"https://arxiv.org/html/{identifier}"
        pdf_url = f"https://arxiv.org/pdf/{identifier}"
        try:
            parser = _PaperHTML()
            parser.feed(_download(html_url).decode("utf-8", errors="replace"))
            content = parser.text()
            if len(content) >= _MIN_TEXT_CHARS:
                return self._result(article, content, html_url, "html")
        except HTTPError as exc:
            if exc.code not in {404, 406, 415}:
                raise RuntimeError(
                    f"Could not retrieve arXiv HTML: {html_url} ({exc.code})"
                ) from None
        except (URLError, TimeoutError):
            raise RuntimeError(f"Could not connect to arXiv HTML: {html_url}") from None

        try:
            data = _download(pdf_url)
            reader = PdfReader(io.BytesIO(data))
            content = "\n\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
        except (HTTPError, URLError, TimeoutError):
            raise RuntimeError(f"Could not retrieve arXiv PDF: {pdf_url}") from None
        if len(content) < _MIN_TEXT_CHARS:
            raise ValueError(
                f"No usable full text found for arXiv article {identifier}"
            )
        return self._result(article, content, pdf_url, "pdf")

    def _result(
        self, article: Article, content: str, url: str, format: str
    ) -> Extraction:
        return Extraction(
            article_id=article.id,
            extractor=self.name,
            extractor_version=self.version,
            kind=self.kind,
            payload={
                "content": content,
                "source_url": url,
                "format": format,
                "word_count": len(content.split()),
            },
        )
