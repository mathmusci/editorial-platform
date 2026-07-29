from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from editorial.explain.common import (
    payload_subset,
    payload_value,
    simple_payload_highlights,
)
from editorial.extractors import ExtractorDescriptor
from editorial.models import Article, Extraction, WorkflowEvent
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)

PROVENANCE_FIELDS = (
    "generated_by",
    "provider",
    "model",
    "prompt_version",
)


class ExtractionInspectionSummary(BaseModel):
    extraction_id: UUID
    created_at: datetime
    article_title: str | None = None
    article_source: str | None = None
    article_url: str | None = None
    extractor: str
    extractor_version: str | None = None
    kind: str
    payload_preview: dict[str, Any]


class ExtractionArtefactInspection(BaseModel):
    extraction: Extraction
    article: Article | None = None
    workflow_events: list[WorkflowEvent]
    payload_highlights: dict[str, Any]
    provenance: dict[str, Any]


class ExtractionCoverageOperation(BaseModel):
    extractor: str
    display_name: str
    expected_kind: str
    status: Literal["present", "missing"]
    extraction_id: UUID | None = None
    extractor_version: str | None = None
    actual_kind: str | None = None
    created_at: datetime | None = None
    payload_highlights: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ArticleExtractionCoverage(BaseModel):
    article_id: UUID
    article_title: str
    article_source: str | None = None
    article_url: str | None = None
    complete: bool
    operations: list[ExtractionCoverageOperation]


class ExtractorCoverageSummary(BaseModel):
    extractor: str
    display_name: str
    expected_kind: str
    present: int
    missing: int


class ExtractionCoverageReport(BaseModel):
    articles_selected: int
    configured_extractors: int
    expected_operations: int
    present: int
    missing: int
    complete_articles: int
    articles_with_missing: int
    by_extractor: list[ExtractorCoverageSummary]
    articles: list[ArticleExtractionCoverage]


class ExtractionInspectionService:
    def __init__(
        self,
        extractions: SQLiteExtractionRepository,
        articles: SQLiteArticleRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.extractions = extractions
        self.articles = articles
        self.workflow_events = workflow_events

    def list(self, limit: int | None = None) -> list[ExtractionInspectionSummary]:
        extractions = self.extractions.list()
        if limit is not None:
            extractions = extractions[:limit]
        return [self._summary_for(extraction) for extraction in extractions]

    def get(self, extraction_id: UUID) -> ExtractionArtefactInspection | None:
        extraction = self.extractions.get(extraction_id)
        if extraction is None:
            return None

        return ExtractionArtefactInspection(
            extraction=extraction,
            article=self.articles.get(extraction.article_id),
            workflow_events=self.workflow_events.list(
                artefact_type="extraction", artefact_id=extraction.id
            ),
            payload_highlights=self._payload_highlights(extraction),
            provenance=self._provenance(extraction),
        )

    def coverage(
        self,
        descriptors: Iterable[ExtractorDescriptor],
        *,
        limit: int | None = None,
        offset: int = 0,
        article_ids: Iterable[UUID] | None = None,
        extractor_keys: Iterable[str] | None = None,
        missing_only: bool = False,
    ) -> ExtractionCoverageReport:
        if limit is not None and limit <= 0:
            raise ValueError("Extraction coverage limit must be a positive integer")
        if offset < 0:
            raise ValueError("Extraction coverage offset must be zero or greater")

        descriptor_list = self._select_descriptors(descriptors, extractor_keys)
        if not descriptor_list:
            raise ValueError("No enabled extractors configured for coverage")
        articles = self._select_articles(article_ids)
        if offset:
            articles = articles[offset:]
        if limit is not None:
            articles = articles[:limit]

        selected_ids = {article.id for article in articles}
        expected = {
            (article.id, descriptor.key, descriptor.kind)
            for article in articles
            for descriptor in descriptor_list
        }
        stored = {
            (extraction.article_id, extraction.extractor, extraction.kind): extraction
            for extraction in self.extractions.list()
            if extraction.article_id in selected_ids
        }

        article_coverage = [
            self._article_coverage(article, descriptor_list, stored)
            for article in articles
        ]
        present = len(expected & stored.keys())
        missing = len(expected) - present
        complete_articles = sum(item.complete for item in article_coverage)
        by_extractor = [
            self._extractor_coverage(descriptor, articles, stored)
            for descriptor in descriptor_list
        ]
        displayed = (
            [item for item in article_coverage if not item.complete]
            if missing_only
            else article_coverage
        )
        return ExtractionCoverageReport(
            articles_selected=len(articles),
            configured_extractors=len(descriptor_list),
            expected_operations=len(expected),
            present=present,
            missing=missing,
            complete_articles=complete_articles,
            articles_with_missing=len(articles) - complete_articles,
            by_extractor=by_extractor,
            articles=displayed,
        )

    def _select_descriptors(
        self,
        descriptors: Iterable[ExtractorDescriptor],
        extractor_keys: Iterable[str] | None,
    ) -> list[ExtractorDescriptor]:
        descriptor_list = list(descriptors)
        if extractor_keys is not None:
            requested = set(extractor_keys)
            selected = [item for item in descriptor_list if item.key in requested]
            missing = requested - {item.key for item in selected}
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise ValueError(f"Configured extractor not found: {missing_text}")
            descriptor_list = selected
        keys = [item.key for item in descriptor_list]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            duplicate_text = ", ".join(sorted(duplicates))
            raise ValueError(
                f"Duplicate configured extractor keys cannot be inspected: {duplicate_text}"
            )
        return descriptor_list

    def _select_articles(self, article_ids: Iterable[UUID] | None) -> list[Article]:
        articles = self.articles.list()
        if article_ids is None:
            return articles
        requested = set(article_ids)
        selected = [article for article in articles if article.id in requested]
        missing = requested - {article.id for article in selected}
        if missing:
            missing_text = ", ".join(str(article_id) for article_id in sorted(missing))
            raise ValueError(
                f"Article not found for extraction coverage: {missing_text}"
            )
        return selected

    def _article_coverage(
        self,
        article: Article,
        descriptors: list[ExtractorDescriptor],
        stored: dict[tuple[UUID, str, str], Extraction],
    ) -> ArticleExtractionCoverage:
        operations = [
            self._coverage_operation(
                descriptor,
                stored.get((article.id, descriptor.key, descriptor.kind)),
            )
            for descriptor in descriptors
        ]
        return ArticleExtractionCoverage(
            article_id=article.id,
            article_title=article.title,
            article_source=article.source,
            article_url=str(article.url) if article.url else None,
            complete=all(item.status == "present" for item in operations),
            operations=operations,
        )

    def _coverage_operation(
        self,
        descriptor: ExtractorDescriptor,
        extraction: Extraction | None,
    ) -> ExtractionCoverageOperation:
        if extraction is None:
            return ExtractionCoverageOperation(
                extractor=descriptor.key,
                display_name=descriptor.display_name,
                expected_kind=descriptor.kind,
                status="missing",
            )
        return ExtractionCoverageOperation(
            extractor=descriptor.key,
            display_name=descriptor.display_name,
            expected_kind=descriptor.kind,
            status="present",
            extraction_id=extraction.id,
            extractor_version=extraction.extractor_version,
            actual_kind=extraction.kind,
            created_at=extraction.created_at,
            payload_highlights=self._payload_highlights(extraction),
            provenance=self._provenance(extraction),
        )

    def _extractor_coverage(
        self,
        descriptor: ExtractorDescriptor,
        articles: list[Article],
        stored: dict[tuple[UUID, str, str], Extraction],
    ) -> ExtractorCoverageSummary:
        present = sum(
            (article.id, descriptor.key, descriptor.kind) in stored
            for article in articles
        )
        return ExtractorCoverageSummary(
            extractor=descriptor.key,
            display_name=descriptor.display_name,
            expected_kind=descriptor.kind,
            present=present,
            missing=len(articles) - present,
        )

    def _summary_for(self, extraction: Extraction) -> ExtractionInspectionSummary:
        article = self.articles.get(extraction.article_id)
        return ExtractionInspectionSummary(
            extraction_id=extraction.id,
            created_at=extraction.created_at,
            article_title=article.title if article else None,
            article_source=article.source if article else None,
            article_url=str(article.url) if article and article.url else None,
            extractor=extraction.extractor,
            extractor_version=extraction.extractor_version,
            kind=extraction.kind,
            payload_preview=self._payload_highlights(extraction),
        )

    def _payload_highlights(self, extraction: Extraction) -> dict[str, Any]:
        if extraction.kind == "reading_time":
            return payload_subset(extraction.payload, ("reading_minutes", "word_count"))
        if extraction.kind == "summary":
            return payload_subset(
                extraction.payload,
                ("summary", "generated_by", "provider", "model", "prompt_version"),
            )
        if extraction.kind in {"keywords", "keyword"}:
            return payload_subset(
                extraction.payload, ("keywords", "extracted_keywords")
            )
        return simple_payload_highlights(extraction.payload, skip_keys=("metadata",))

    def _provenance(self, extraction: Extraction) -> dict[str, Any]:
        provenance: dict[str, Any] = {}
        for field in PROVENANCE_FIELDS:
            value = payload_value(extraction.payload, field)
            if value is not None:
                provenance[field] = value
        return provenance
