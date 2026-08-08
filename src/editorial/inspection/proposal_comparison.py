from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from editorial.inspection.proposals import (
    ProposalArticleInspection,
    ProposalInspection,
    ProposalInspectionService,
)
from editorial.models import ConstraintResult, OptimisationRequest


class ProposalArticleEvidence(BaseModel):
    source: str | None = None
    reading_minutes: int | float | None = None
    relevance_score: float | None = None
    origin: Literal["proposal_snapshot", "current_stored_evidence", "missing"]


class ProposalArticleComparison(BaseModel):
    article_id: UUID
    title: str
    status: Literal["shared", "added", "removed"]
    moved: bool = False
    base_position: int | None = None
    candidate_position: int | None = None
    base_evidence: ProposalArticleEvidence | None = None
    candidate_evidence: ProposalArticleEvidence | None = None


class ProposalComparisonSide(BaseModel):
    proposal_id: UUID
    optimisation_request_id: UUID | None = None
    optimiser: str
    optimiser_version: str | None = None
    publication_name: str | None = None
    strategy: str | None = None
    objective_value: float
    article_count: int
    known_reading_minutes: float
    articles_missing_reading_time: int


class ProposalValueDifference(BaseModel):
    field: str
    base_present: bool
    base_value: Any = None
    candidate_present: bool
    candidate_value: Any = None


class ProposalConstraintComparison(BaseModel):
    name: str
    kind: str
    status: Literal["unchanged", "changed", "added", "removed"]
    base: ConstraintResult | None = None
    candidate: ConstraintResult | None = None


class ProposalComparisonReport(BaseModel):
    base: ProposalComparisonSide
    candidate: ProposalComparisonSide
    objective_delta: float
    shared_articles: int
    added_articles: int
    removed_articles: int
    moved_articles: int
    articles: list[ProposalArticleComparison]
    request_differences: list[ProposalValueDifference] = Field(default_factory=list)
    constraints: list[ProposalConstraintComparison] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class ProposalComparisonService:
    def __init__(self, inspections: ProposalInspectionService):
        self.inspections = inspections

    def compare(
        self, base_proposal_id: UUID, candidate_proposal_id: UUID
    ) -> ProposalComparisonReport:
        if base_proposal_id == candidate_proposal_id:
            raise ValueError("Proposal comparison requires two different proposal IDs")

        base = self._inspection(base_proposal_id)
        candidate = self._inspection(candidate_proposal_id)
        evidence_gaps: list[str] = []
        articles = self._articles(base, candidate, evidence_gaps)
        base_side = self._side(base, articles, "base")
        candidate_side = self._side(candidate, articles, "candidate")

        if base.optimisation_request is None:
            evidence_gaps.append(
                f"Base proposal {base.proposal.id} has no linked optimisation request."
            )
        if candidate.optimisation_request is None:
            evidence_gaps.append(
                "Candidate proposal "
                f"{candidate.proposal.id} has no linked optimisation request."
            )

        return ProposalComparisonReport(
            base=base_side,
            candidate=candidate_side,
            objective_delta=round(
                candidate.proposal.objective_value - base.proposal.objective_value,
                2,
            ),
            shared_articles=sum(item.status == "shared" for item in articles),
            added_articles=sum(item.status == "added" for item in articles),
            removed_articles=sum(item.status == "removed" for item in articles),
            moved_articles=sum(item.moved for item in articles),
            articles=articles,
            request_differences=self._request_differences(
                base.optimisation_request,
                candidate.optimisation_request,
            ),
            constraints=self._constraint_comparisons(base, candidate),
            evidence_gaps=list(dict.fromkeys(evidence_gaps)),
        )

    def _inspection(self, proposal_id: UUID) -> ProposalInspection:
        inspection = self.inspections.get(proposal_id)
        if inspection is None:
            raise ValueError(f"Issue proposal not found: {proposal_id}")
        return inspection

    def _articles(
        self,
        base: ProposalInspection,
        candidate: ProposalInspection,
        evidence_gaps: list[str],
    ) -> list[ProposalArticleComparison]:
        base_positions = {
            article_id: position
            for position, article_id in enumerate(base.proposal.article_ids, start=1)
        }
        candidate_positions = {
            article_id: position
            for position, article_id in enumerate(
                candidate.proposal.article_ids, start=1
            )
        }
        base_articles = {
            article.article_id: article for article in base.selected_articles
        }
        candidate_articles = {
            article.article_id: article for article in candidate.selected_articles
        }
        ordered_ids = [
            *base.proposal.article_ids,
            *[
                article_id
                for article_id in candidate.proposal.article_ids
                if article_id not in base_positions
            ],
        ]
        comparisons = []
        for article_id in ordered_ids:
            base_position = base_positions.get(article_id)
            candidate_position = candidate_positions.get(article_id)
            if base_position is None:
                status = "added"
            elif candidate_position is None:
                status = "removed"
            else:
                status = "shared"
            title = self._article_title(
                base_articles.get(article_id), candidate_articles.get(article_id)
            )
            base_evidence = self._evidence(
                "Base",
                base,
                article_id,
                base_articles.get(article_id),
                evidence_gaps,
            )
            candidate_evidence = self._evidence(
                "Candidate",
                candidate,
                article_id,
                candidate_articles.get(article_id),
                evidence_gaps,
            )
            comparisons.append(
                ProposalArticleComparison(
                    article_id=article_id,
                    title=title,
                    status=status,
                    moved=(status == "shared" and base_position != candidate_position),
                    base_position=base_position,
                    candidate_position=candidate_position,
                    base_evidence=base_evidence,
                    candidate_evidence=candidate_evidence,
                )
            )
        return comparisons

    def _article_title(
        self,
        base: ProposalArticleInspection | None,
        candidate: ProposalArticleInspection | None,
    ) -> str:
        article = base or candidate
        if article is None or article.missing:
            return "Missing article"
        return article.title

    def _evidence(
        self,
        side_name: str,
        inspection: ProposalInspection,
        article_id: UUID,
        article: ProposalArticleInspection | None,
        evidence_gaps: list[str],
    ) -> ProposalArticleEvidence | None:
        if article_id not in inspection.proposal.article_ids:
            return None

        snapshot = self._snapshot_for(inspection, article_id)
        if snapshot is not None:
            evidence = ProposalArticleEvidence(
                source=self._text(snapshot.get("source")),
                reading_minutes=self._number(snapshot.get("reading_minutes")),
                relevance_score=self._number(snapshot.get("relevance_score")),
                origin="proposal_snapshot",
            )
        elif article is None or article.missing:
            evidence = ProposalArticleEvidence(origin="missing")
            evidence_gaps.append(
                f"{side_name} proposal references missing article {article_id}."
            )
        else:
            evidence = ProposalArticleEvidence(
                source=article.source,
                reading_minutes=article.reading_minutes,
                relevance_score=article.relevance_score,
                origin="current_stored_evidence",
            )
            evidence_gaps.append(
                f"{side_name} proposal has no evidence snapshot for {article_id}; "
                "current stored evidence is shown."
            )

        if evidence.reading_minutes is None:
            evidence_gaps.append(
                f"{side_name} proposal has no reading time for {article_id}."
            )
        if evidence.relevance_score is None:
            evidence_gaps.append(
                f"{side_name} proposal has no relevance score for {article_id}."
            )
        return evidence

    def _snapshot_for(
        self, inspection: ProposalInspection, article_id: UUID
    ) -> dict[str, Any] | None:
        selected = inspection.proposal.metadata.get("selected")
        if not isinstance(selected, list):
            return None
        for item in selected:
            if not isinstance(item, dict):
                continue
            try:
                selected_id = UUID(str(item.get("article_id")))
            except (TypeError, ValueError):
                continue
            if selected_id == article_id:
                return item
        return None

    def _side(
        self,
        inspection: ProposalInspection,
        articles: list[ProposalArticleComparison],
        side: Literal["base", "candidate"],
    ) -> ProposalComparisonSide:
        evidence = [
            getattr(article, f"{side}_evidence")
            for article in articles
            if getattr(article, f"{side}_position") is not None
        ]
        reading_minutes = [
            item.reading_minutes
            for item in evidence
            if item is not None and item.reading_minutes is not None
        ]
        request = inspection.optimisation_request
        return ProposalComparisonSide(
            proposal_id=inspection.proposal.id,
            optimisation_request_id=request.id if request else None,
            optimiser=inspection.proposal.optimiser,
            optimiser_version=inspection.proposal.optimiser_version,
            publication_name=inspection.publication_name,
            strategy=request.strategy if request else None,
            objective_value=inspection.proposal.objective_value,
            article_count=len(inspection.proposal.article_ids),
            known_reading_minutes=float(sum(reading_minutes)),
            articles_missing_reading_time=len(evidence) - len(reading_minutes),
        )

    def _request_differences(
        self,
        base: OptimisationRequest | None,
        candidate: OptimisationRequest | None,
    ) -> list[ProposalValueDifference]:
        base_values = self._request_values(base)
        candidate_values = self._request_values(candidate)
        differences = []
        for field in sorted(set(base_values) | set(candidate_values)):
            base_present = field in base_values
            candidate_present = field in candidate_values
            base_value = base_values.get(field)
            candidate_value = candidate_values.get(field)
            if base_present == candidate_present and base_value == candidate_value:
                continue
            differences.append(
                ProposalValueDifference(
                    field=field,
                    base_present=base_present,
                    base_value=base_value,
                    candidate_present=candidate_present,
                    candidate_value=candidate_value,
                )
            )
        return differences

    def _request_values(self, request: OptimisationRequest | None) -> dict[str, Any]:
        if request is None:
            return {}
        values = {
            "publication": request.publication,
            "strategy": request.strategy,
            "settings": request.settings,
            "constraints": request.constraints,
            "goals": request.goals,
            "preferences": request.preferences,
            "created_by": request.created_by,
            "parent_request_id": request.parent_request_id,
            "parent_proposal_id": request.parent_proposal_id,
        }
        flattened: dict[str, Any] = {}
        for field, value in values.items():
            self._flatten(field, value, flattened)
        return flattened

    def _flatten(self, prefix: str, value: Any, result: dict[str, Any]) -> None:
        if isinstance(value, dict) and value:
            for key in sorted(value):
                self._flatten(f"{prefix}.{key}", value[key], result)
            return
        result[prefix] = value

    def _constraint_comparisons(
        self, base: ProposalInspection, candidate: ProposalInspection
    ) -> list[ProposalConstraintComparison]:
        base_constraints = {
            (item.name, item.kind): item for item in base.constraint_results
        }
        candidate_constraints = {
            (item.name, item.kind): item for item in candidate.constraint_results
        }
        comparisons = []
        for name, kind in sorted(set(base_constraints) | set(candidate_constraints)):
            base_result = base_constraints.get((name, kind))
            candidate_result = candidate_constraints.get((name, kind))
            if base_result is None:
                status = "added"
            elif candidate_result is None:
                status = "removed"
            elif base_result == candidate_result:
                status = "unchanged"
            else:
                status = "changed"
            comparisons.append(
                ProposalConstraintComparison(
                    name=name,
                    kind=kind,
                    status=status,
                    base=base_result,
                    candidate=candidate_result,
                )
            )
        return comparisons

    def _number(self, value: Any) -> int | float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            return value
        return None

    def _text(self, value: Any) -> str | None:
        return value if isinstance(value, str) else None
