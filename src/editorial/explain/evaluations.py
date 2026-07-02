from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from editorial.inspection import EvaluationInspection
from editorial.inspection.evaluations import EvaluationInspectionService
from editorial.models import Extraction
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
)

PROVENANCE_FIELDS = (
    "generated_by",
    "provider",
    "model",
    "prompt_version",
    "token_usage",
    "latency",
    "cost",
)


class EvaluationEvidence(BaseModel):
    evidence_type: Literal["evaluation", "extraction"]
    kind: str
    source: str
    highlights: dict[str, Any]


class EvaluationProvenance(BaseModel):
    fields: dict[str, Any]
    evaluator_type: str


class EvaluationInterpretation(BaseModel):
    summary: str
    confidence_note: str | None = None


class RelatedProposal(BaseModel):
    proposal_id: UUID
    optimiser: str
    objective_value: float


class RelatedPublication(BaseModel):
    publication_id: UUID
    title: str
    proposal_id: UUID


class NextAction(BaseModel):
    label: str
    command: str


class EvaluationExplanation(BaseModel):
    evaluation_id: UUID
    article_id: UUID
    article_title: str | None = None
    article_source: str | None = None
    evaluator: str
    evaluator_version: str | None = None
    kind: str
    created_at: datetime
    score: float | None = None
    confidence: float | None = None
    rationale: str | None = None
    decision: Any = None
    outcome_summary: str
    evidence: list[EvaluationEvidence]
    provenance: EvaluationProvenance
    interpretation: EvaluationInterpretation
    limitations: list[str]
    related_proposals: list[RelatedProposal]
    related_publications: list[RelatedPublication]
    next_actions: list[NextAction]


class EvaluationExplanationService:
    def __init__(
        self,
        evaluation_inspections: EvaluationInspectionService,
        proposals: SQLiteIssueProposalRepository,
        publications: SQLitePublicationRepository,
    ):
        self.evaluation_inspections = evaluation_inspections
        self.proposals = proposals
        self.publications = publications

    def get(self, evaluation_id: UUID) -> EvaluationExplanation | None:
        inspection = self.evaluation_inspections.get(evaluation_id)
        if inspection is None:
            return None
        return self.build(inspection)

    def build(self, inspection: EvaluationInspection) -> EvaluationExplanation:
        evaluation = inspection.evaluation
        provenance = self._provenance(inspection)
        related_proposals = self._related_proposals(evaluation.article_id)
        related_publications = self._related_publications(
            evaluation.article_id, related_proposals
        )
        return EvaluationExplanation(
            evaluation_id=evaluation.id,
            article_id=evaluation.article_id,
            article_title=inspection.article.title if inspection.article else None,
            article_source=inspection.article.source if inspection.article else None,
            evaluator=evaluation.evaluator,
            evaluator_version=evaluation.evaluator_version,
            kind=evaluation.kind,
            created_at=evaluation.created_at,
            score=evaluation.score,
            confidence=evaluation.confidence,
            rationale=evaluation.rationale,
            decision=self._payload_value(evaluation.payload, "decision"),
            outcome_summary=self._outcome_summary(inspection),
            evidence=self._evidence(inspection),
            provenance=provenance,
            interpretation=self._interpretation(inspection, provenance),
            limitations=self._limitations(inspection, provenance),
            related_proposals=related_proposals,
            related_publications=related_publications,
            next_actions=self._next_actions(
                evaluation.id, evaluation.article_id, related_proposals
            ),
        )

    def _outcome_summary(self, inspection: EvaluationInspection) -> str:
        evaluation = inspection.evaluation
        if evaluation.score is not None and evaluation.confidence is not None:
            return (
                f"This evaluation assigned a {evaluation.kind} score of "
                f"{evaluation.score} with confidence {evaluation.confidence}."
            )
        if evaluation.score is not None:
            return (
                f"This evaluation assigned a {evaluation.kind} score of "
                f"{evaluation.score}."
            )
        if evaluation.confidence is not None:
            return (
                f"This evaluation recorded confidence {evaluation.confidence} "
                f"for {evaluation.kind}."
            )
        return f"This evaluation recorded a {evaluation.kind} assessment."

    def _evidence(self, inspection: EvaluationInspection) -> list[EvaluationEvidence]:
        evaluation = inspection.evaluation
        evidence: list[EvaluationEvidence] = []
        evaluation_highlights = self._evaluation_highlights(inspection)
        if evaluation_highlights:
            evidence.append(
                EvaluationEvidence(
                    evidence_type="evaluation",
                    kind=evaluation.kind,
                    source=evaluation.evaluator,
                    highlights=evaluation_highlights,
                )
            )
        for extraction in inspection.extractions:
            highlights = self._extraction_highlights(extraction)
            if highlights:
                evidence.append(
                    EvaluationEvidence(
                        evidence_type="extraction",
                        kind=extraction.kind,
                        source=extraction.extractor,
                        highlights=highlights,
                    )
                )
        return evidence

    def _evaluation_highlights(
        self, inspection: EvaluationInspection
    ) -> dict[str, Any]:
        evaluation = inspection.evaluation
        highlights: dict[str, Any] = {}
        if evaluation.rationale is not None:
            highlights["rationale"] = evaluation.rationale
        for key in (
            "reasoning",
            "evidence",
            "summary",
            "keywords",
            "extracted_keywords",
            "decision",
        ):
            value = self._payload_value(evaluation.payload, key)
            if value is not None:
                highlights[key] = value
        for key, value in inspection.payload_highlights.items():
            highlights.setdefault(key, value)
        return highlights

    def _extraction_highlights(self, extraction: Extraction) -> dict[str, Any]:
        if extraction.kind == "reading_time":
            return self._payload_subset(
                extraction.payload, ("reading_minutes", "word_count")
            )
        if extraction.kind == "summary":
            return self._payload_subset(extraction.payload, ("summary",))
        if extraction.kind in {"keywords", "keyword"}:
            return self._payload_subset(
                extraction.payload, ("keywords", "extracted_keywords")
            )
        return self._simple_highlights(extraction.payload)

    def _provenance(self, inspection: EvaluationInspection) -> EvaluationProvenance:
        fields = dict(inspection.ai_provenance)
        for key in PROVENANCE_FIELDS:
            value = self._payload_value(inspection.evaluation.payload, key)
            if value is not None:
                fields[key] = value
        generated_by = fields.get("generated_by")
        evaluator_type = (
            "ai"
            if generated_by == "llm" or fields.get("provider") or fields.get("model")
            else "deterministic"
        )
        return EvaluationProvenance(fields=fields, evaluator_type=evaluator_type)

    def _interpretation(
        self,
        inspection: EvaluationInspection,
        provenance: EvaluationProvenance,
    ) -> EvaluationInterpretation:
        evaluation = inspection.evaluation
        if provenance.evaluator_type == "ai":
            summary = (
                "This score was generated by an AI evaluator using recorded "
                "provenance fields."
            )
        else:
            summary = (
                f"This score was produced by the {evaluation.evaluator} evaluator."
            )

        confidence_note = None
        if evaluation.confidence is not None:
            confidence_note = (
                f"The stored confidence is {evaluation.confidence}. No additional "
                "confidence semantics are inferred."
            )
        return EvaluationInterpretation(
            summary=summary,
            confidence_note=confidence_note,
        )

    def _limitations(
        self,
        inspection: EvaluationInspection,
        provenance: EvaluationProvenance,
    ) -> list[str]:
        evaluation = inspection.evaluation
        limitations: list[str] = []
        if evaluation.rationale is None and not self._payload_value(
            evaluation.payload, "reasoning"
        ):
            limitations.append("No rationale or reasoning was recorded.")
        if evaluation.confidence is None:
            limitations.append("Confidence unavailable.")
        if not provenance.fields:
            limitations.append("No provenance recorded.")
        if not inspection.payload_highlights and not evaluation.rationale:
            limitations.append("No evaluation evidence was recorded.")
        if not inspection.extractions:
            limitations.append("No related extractions were recorded.")
        if inspection.article is None:
            limitations.append("Related Article was not found.")
        if not limitations:
            limitations.append(
                "The explanation is limited to stored artefacts and does not "
                "recreate evaluator reasoning."
            )
        return limitations

    def _related_proposals(self, article_id: UUID) -> list[RelatedProposal]:
        return [
            RelatedProposal(
                proposal_id=proposal.id,
                optimiser=proposal.optimiser,
                objective_value=proposal.objective_value,
            )
            for proposal in self.proposals.list()
            if article_id in proposal.article_ids
        ]

    def _related_publications(
        self,
        article_id: UUID,
        proposals: list[RelatedProposal],
    ) -> list[RelatedPublication]:
        proposal_ids = {proposal.proposal_id for proposal in proposals}
        publications: list[RelatedPublication] = []
        for publication in self.publications.list():
            article_in_publication = any(
                article_id in section.article_ids for section in publication.sections
            )
            if article_in_publication or publication.proposal_id in proposal_ids:
                publications.append(
                    RelatedPublication(
                        publication_id=publication.id,
                        title=publication.title,
                        proposal_id=publication.proposal_id,
                    )
                )
        return publications

    def _next_actions(
        self,
        evaluation_id: UUID,
        article_id: UUID,
        proposals: list[RelatedProposal],
    ) -> list[NextAction]:
        actions = [
            NextAction(
                label="Inspect evaluation",
                command=f"editorial evaluation show {evaluation_id} --db <db>",
            ),
            NextAction(
                label="Inspect article",
                command=f"editorial article show {article_id} --db <db>",
            ),
        ]
        for proposal in proposals[:3]:
            actions.append(
                NextAction(
                    label="Inspect proposal",
                    command=(
                        f"editorial proposal show {proposal.proposal_id} --db <db>"
                    ),
                )
            )
            actions.append(
                NextAction(
                    label="Explain article selection",
                    command=(
                        "editorial explain article-selection "
                        f"{proposal.proposal_id} {article_id} --db <db>"
                    ),
                )
            )
        return actions

    def _payload_subset(
        self, payload: dict[str, Any], keys: tuple[str, ...]
    ) -> dict[str, Any]:
        return {key: payload[key] for key in keys if key in payload}

    def _simple_highlights(self, payload: dict[str, Any]) -> dict[str, Any]:
        highlights: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "metadata":
                continue
            if isinstance(value, str | int | float | bool) or value is None:
                highlights[key] = value
            if len(highlights) >= 4:
                break
        return highlights

    def _payload_value(self, payload: dict[str, Any], key: str) -> Any:
        if key in payload:
            return payload[key]
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and key in metadata:
            return metadata[key]
        return None
