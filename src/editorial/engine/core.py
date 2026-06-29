from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from editorial.interfaces import Provider
from editorial.storage import SQLiteArticleRepository


@dataclass(frozen=True)
class IngestResult:
    fetched: int
    inserted: int
    skipped_duplicates: int


class EditorialEngine:
    def __init__(self, article_repository: SQLiteArticleRepository):
        self.article_repository = article_repository

    def ingest(self, providers: Iterable[Provider]) -> IngestResult:
        fetched = inserted = skipped = 0
        for provider in providers:
            for article in provider.fetch():
                fetched += 1
                if self.article_repository.upsert(article):
                    inserted += 1
                else:
                    skipped += 1
        return IngestResult(fetched, inserted, skipped)
