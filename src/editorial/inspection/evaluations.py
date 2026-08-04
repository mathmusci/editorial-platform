from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import Article, Evaluation, Extraction, WorkflowEvent
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteWorkflowEventRepository,
)

COMMON_PAYLOAD_FIELDS = (
    "rationale",
    "reasoning",
    "confidence",
    "evidence",
    "dimensions",
    "issues",
    "summary_extraction_id",
    "summary_extractor",
)
AI_PROVENANCE_FIELDS = (
    "generated_by",
    "provider",
    "model",
    "prompt_version",
)


class EvaluationInspectionSummary(BaseModel):
    evaluation_id: UUID
    created_at: datetime
    article_title: str | None = None
    article_source: str | None = None
    evaluator: str
    kind: str
    score: float | None = None
    confidence: float | None = None


class EvaluationInspection(BaseModel):
    evaluation: Evaluation
    article: Article | None = None
    extractions: list[Extraction]
    workflow_events: list[WorkflowEvent]
    payload_highlights: dict[str, Any]
    ai_provenance: dict[str, Any]


class EvaluationInspectionService:
    def __init__(
        self,
        evaluations: SQLiteEvaluationRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.evaluations = evaluations
        self.articles = articles
        self.extractions = extractions
        self.workflow_events = workflow_events

    def list(self, limit: int | None = None) -> list[EvaluationInspectionSummary]:
        evaluations = self.evaluations.list()
        if limit is not None:
            evaluations = evaluations[:limit]
        return [self._summary_for(evaluation) for evaluation in evaluations]

    def get(self, evaluation_id: UUID) -> EvaluationInspection | None:
        evaluation = self.evaluations.get(evaluation_id)
        if evaluation is None:
            return None

        return EvaluationInspection(
            evaluation=evaluation,
            article=self.articles.get(evaluation.article_id),
            extractions=self.extractions.list(article_id=evaluation.article_id),
            workflow_events=self.workflow_events.list(
                artefact_type="evaluation", artefact_id=evaluation.id
            ),
            payload_highlights=self._payload_highlights(evaluation),
            ai_provenance=self._ai_provenance(evaluation),
        )

    def _summary_for(self, evaluation: Evaluation) -> EvaluationInspectionSummary:
        article = self.articles.get(evaluation.article_id)
        return EvaluationInspectionSummary(
            evaluation_id=evaluation.id,
            created_at=evaluation.created_at,
            article_title=article.title if article else None,
            article_source=article.source if article else None,
            evaluator=evaluation.evaluator,
            kind=evaluation.kind,
            score=evaluation.score,
            confidence=evaluation.confidence,
        )

    def _payload_highlights(self, evaluation: Evaluation) -> dict[str, Any]:
        highlights: dict[str, Any] = {}
        for field in COMMON_PAYLOAD_FIELDS:
            value = self._payload_value(evaluation.payload, field)
            if value is not None:
                highlights[field] = value
        return highlights

    def _ai_provenance(self, evaluation: Evaluation) -> dict[str, Any]:
        provenance: dict[str, Any] = {}
        for field in AI_PROVENANCE_FIELDS:
            value = self._payload_value(evaluation.payload, field)
            if value is not None:
                provenance[field] = value
        return provenance

    def _payload_value(self, payload: dict[str, Any], key: str) -> Any:
        if key in payload:
            return payload[key]
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and key in metadata:
            return metadata[key]
        return None
