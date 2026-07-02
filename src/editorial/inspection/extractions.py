from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.explain.common import (
    payload_subset,
    payload_value,
    simple_payload_highlights,
)
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
