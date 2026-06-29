from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID
from editorial.models import Article, EditorialStatus


class SQLiteArticleRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT UNIQUE, source TEXT,
                published_at TEXT, authors_json TEXT NOT NULL, summary TEXT, content TEXT,
                status TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)")

    def upsert(self, article: Article) -> bool:
        with self._connect() as conn:
            if article.url is not None:
                existing = conn.execute("SELECT id FROM articles WHERE url = ?", (str(article.url),)).fetchone()
                if existing:
                    return False
            conn.execute("""INSERT INTO articles (id, title, url, source, published_at, authors_json, summary, content, status, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                str(article.id), article.title, str(article.url) if article.url else None, article.source,
                article.published_at.isoformat() if article.published_at else None, json.dumps(article.authors),
                article.summary, article.content, article.status.value, json.dumps(article.metadata),
                article.created_at.isoformat(), article.updated_at.isoformat()))
            return True

    def list(self, status: EditorialStatus | None = None, limit: int | None = None) -> list[Article]:
        query = "SELECT * FROM articles"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY published_at DESC, created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_article(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
        return int(row["n"])

    def get(self, article_id: UUID) -> Article | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (str(article_id),)).fetchone()
        return self._row_to_article(row) if row else None

    def _row_to_article(self, row: sqlite3.Row) -> Article:
        return Article.model_validate({"id": row["id"], "title": row["title"], "url": row["url"], "source": row["source"], "published_at": row["published_at"], "authors": json.loads(row["authors_json"]), "summary": row["summary"], "content": row["content"], "status": row["status"], "metadata": json.loads(row["metadata_json"]), "created_at": row["created_at"], "updated_at": row["updated_at"]})
