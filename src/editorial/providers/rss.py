from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import feedparser

from editorial.models import Article


class RSSProvider:
    name = "rss"
    version = "0.1.0"

    def __init__(
        self,
        url: str | None = None,
        path: str | Path | None = None,
        source: str | None = None,
        base_path: str | Path | None = None,
    ):
        if not url and not path:
            raise ValueError("RSS provider requires either 'url' or 'path'")
        self.url = url
        self.path = Path(path) if path is not None else None
        self.source = source
        self.base_path = Path(base_path) if base_path is not None else None

    def fetch(self) -> Iterable[Article]:
        feed = self._parse_feed()
        feed_title = self.source or feed.feed.get("title")
        for entry in feed.entries:
            article = self._entry_to_article(entry, feed_title)
            if article is not None:
                yield article

    def _parse_feed(self) -> Any:
        if self.path is not None:
            feed_path = self.path
            if not feed_path.is_absolute() and self.base_path is not None:
                feed_path = self.base_path / feed_path
            return feedparser.parse(feed_path.read_bytes())
        return feedparser.parse(self.url)

    def _entry_to_article(self, entry: Any, feed_title: str | None) -> Article | None:
        title = entry.get("title")
        link = entry.get("link")
        if not title or not link:
            return None

        return Article(
            title=title,
            url=link,
            source=feed_title,
            published_at=self._published_at(entry),
            authors=self._authors(entry),
            summary=entry.get("summary"),
            content=self._content(entry),
            metadata={
                "rss_id": entry.get("id"),
                "rss_tags": [tag.get("term") for tag in entry.get("tags", []) if tag.get("term")],
            },
        )

    def _published_at(self, entry: Any) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime(*parsed[:6], tzinfo=timezone.utc)

    def _authors(self, entry: Any) -> list[str]:
        authors = entry.get("authors")
        if authors:
            return [author.get("name") for author in authors if author.get("name")]
        author = entry.get("author")
        return [author] if author else []

    def _content(self, entry: Any) -> str | None:
        content = entry.get("content")
        if content:
            return content[0].get("value")
        return None
