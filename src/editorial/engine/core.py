from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from editorial.interfaces import Extractor, Provider
from editorial.storage import SQLiteArticleRepository, SQLiteExtractionRepository


@dataclass(frozen=True)
class IngestResult:
    fetched: int
    inserted: int
    skipped_duplicates: int


@dataclass(frozen=True)
class ExtractionRunResult:
    articles: int
    extractors: int
    stored: int


class EditorialEngine:
    def __init__(
        self,
        article_repository: SQLiteArticleRepository,
        extraction_repository: SQLiteExtractionRepository | None = None,
    ):
        self.article_repository = article_repository
        self.extraction_repository = extraction_repository

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

    def extract(self, extractors: Iterable[Extractor]) -> ExtractionRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run extractors")

        extractor_list = list(extractors)
        articles = self.article_repository.list()
        stored = 0
        for article in articles:
            for extractor in extractor_list:
                extraction = extractor.extract(article)
                self.extraction_repository.insert(extraction)
                stored += 1
        return ExtractionRunResult(
            articles=len(articles), extractors=len(extractor_list), stored=stored
        )
