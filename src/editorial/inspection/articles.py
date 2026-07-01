from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteWorkflowEventRepository,
)

AI_PROVENANCE_FIELDS = (
    "generated_by",
    "provider",
    "model",
    "prompt_version",
)


class ArticleInspectionSummary(BaseModel):
    article_id: UUID
    title: str
    source: str | None = None
    status: str
    published_at: datetime | None = None
    url: str | None = None
    extraction_count: int = 0
    evaluation_count: int = 0


class ExtractionInspection(BaseModel):
    extraction: Extraction
    payload_highlights: dict[str, Any]
    ai_provenance: dict[str, Any]


class EvaluationArticleInspection(BaseModel):
    evaluation: Evaluation
    ai_provenance: dict[str, Any]


class ArticleInspection(BaseModel):
    article: Article
    extractions: list[ExtractionInspection]
    evaluations: list[EvaluationArticleInspection]
    proposals: list[IssueProposal]
    publications: list[Publication]
    workflow_events: list[WorkflowEvent]


class ArticleInspectionService:
    def __init__(
        self,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        evaluations: SQLiteEvaluationRepository,
        proposals: SQLiteIssueProposalRepository,
        publications: SQLitePublicationRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.articles = articles
        self.extractions = extractions
        self.evaluations = evaluations
        self.proposals = proposals
        self.publications = publications
        self.workflow_events = workflow_events

    def list(self, limit: int | None = None) -> list[ArticleInspectionSummary]:
        return [
            self._summary_for(article) for article in self.articles.list(limit=limit)
        ]

    def get(self, article_id: UUID) -> ArticleInspection | None:
        article = self.articles.get(article_id)
        if article is None:
            return None

        return ArticleInspection(
            article=article,
            extractions=[
                ExtractionInspection(
                    extraction=extraction,
                    payload_highlights=self._extraction_highlights(extraction),
                    ai_provenance=self._ai_provenance(extraction.payload),
                )
                for extraction in self.extractions.list(article_id=article_id)
            ],
            evaluations=[
                EvaluationArticleInspection(
                    evaluation=evaluation,
                    ai_provenance=self._ai_provenance(evaluation.payload),
                )
                for evaluation in self.evaluations.list(article_id=article_id)
            ],
            proposals=self._proposals_for(article_id),
            publications=self._publications_for(article_id),
            workflow_events=self.workflow_events.list(
                artefact_type="article", artefact_id=article_id
            ),
        )

    def _summary_for(self, article: Article) -> ArticleInspectionSummary:
        return ArticleInspectionSummary(
            article_id=article.id,
            title=article.title,
            source=article.source,
            status=article.status.value,
            published_at=article.published_at,
            url=str(article.url) if article.url else None,
            extraction_count=len(self.extractions.list(article_id=article.id)),
            evaluation_count=len(self.evaluations.list(article_id=article.id)),
        )

    def _proposals_for(self, article_id: UUID) -> list[IssueProposal]:
        return [
            proposal
            for proposal in self.proposals.list()
            if article_id in proposal.article_ids
        ]

    def _publications_for(self, article_id: UUID) -> list[Publication]:
        publications: list[Publication] = []
        for publication in self.publications.list():
            if any(
                article_id in section.article_ids for section in publication.sections
            ):
                publications.append(publication)
        return publications

    def _extraction_highlights(self, extraction: Extraction) -> dict[str, Any]:
        if extraction.kind == "reading_time":
            return self._payload_subset(
                extraction.payload, ("reading_minutes", "word_count")
            )
        if extraction.kind == "summary":
            return self._payload_subset(extraction.payload, ("summary",))
        return {}

    def _ai_provenance(self, payload: dict[str, Any]) -> dict[str, Any]:
        provenance: dict[str, Any] = {}
        for field in AI_PROVENANCE_FIELDS:
            value = self._payload_value(payload, field)
            if value is not None:
                provenance[field] = value
        return provenance

    def _payload_subset(
        self, payload: dict[str, Any], keys: tuple[str, ...]
    ) -> dict[str, Any]:
        return {key: payload[key] for key in keys if key in payload}

    def _payload_value(self, payload: dict[str, Any], key: str) -> Any:
        if key in payload:
            return payload[key]
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and key in metadata:
            return metadata[key]
        return None
