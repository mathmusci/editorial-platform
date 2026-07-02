from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.inspection import PublicationInspection
from editorial.inspection.publications import PublicationInspectionService


class PublicationIdentity(BaseModel):
    publication_id: UUID
    title: str
    subtitle: str | None = None
    created_at: datetime
    proposal_id: UUID
    optimisation_request_id: UUID | None = None
    status: str | None = None


class PublicationComposition(BaseModel):
    section_count: int
    section_titles: list[str]
    article_count: int
    source_counts: dict[str, int]
    total_reading_minutes: int | float | None = None
    average_relevance_score: float | None = None
    missing_evaluation_count: int
    missing_reading_time_count: int


class PublicationEditorialContext(BaseModel):
    proposal_objective_value: float | None = None
    satisfied_constraint_count: int
    failed_constraint_count: int
    largest_penalties: list[tuple[str, float]]
    review_decisions: list[str]
    review_comments: list[str]
    metadata: dict[str, Any]


class PublicationWorkflowSummary(BaseModel):
    events: list[str]
    rendered_output_count: int


class PublicationEvidence(BaseModel):
    summary: str
    workflow: PublicationWorkflowSummary
    editorial_context: PublicationEditorialContext


class PublicationLimitations(BaseModel):
    items: list[str]


class NextAction(BaseModel):
    label: str
    command: str


class PublicationExplanation(BaseModel):
    identity: PublicationIdentity
    editorial_summary: str
    composition: PublicationComposition
    evidence: PublicationEvidence
    interpretation: str
    limitations: PublicationLimitations
    related_artefacts: dict[str, list[str]]
    next_actions: list[NextAction]


class PublicationExplanationService:
    def __init__(self, publication_inspections: PublicationInspectionService):
        self.publication_inspections = publication_inspections

    def get(self, publication_id: UUID) -> PublicationExplanation | None:
        inspection = self.publication_inspections.get(publication_id)
        if inspection is None:
            return None
        return self.build(inspection)

    def build(self, inspection: PublicationInspection) -> PublicationExplanation:
        identity = self._identity(inspection)
        composition = self._composition(inspection)
        evidence = self._evidence(inspection)
        return PublicationExplanation(
            identity=identity,
            editorial_summary=self._editorial_summary(
                inspection, composition, evidence
            ),
            composition=composition,
            evidence=evidence,
            interpretation=self._interpretation(composition),
            limitations=self._limitations(inspection, composition),
            related_artefacts=self._related_artefacts(inspection, composition),
            next_actions=self._next_actions(inspection),
        )

    def _identity(self, inspection: PublicationInspection) -> PublicationIdentity:
        status = "rendered" if inspection.rendered_outputs else None
        if status is None and inspection.publication_workflow_events:
            status = "created"
        return PublicationIdentity(
            publication_id=inspection.publication.id,
            title=inspection.publication.title,
            subtitle=inspection.publication.subtitle,
            created_at=inspection.publication.created_at,
            proposal_id=inspection.publication.proposal_id,
            optimisation_request_id=(
                inspection.optimisation_request.id
                if inspection.optimisation_request
                else None
            ),
            status=status,
        )

    def _composition(self, inspection: PublicationInspection) -> PublicationComposition:
        article_items = [
            article for section in inspection.sections for article in section.articles
        ]
        reading_times = [
            article.reading_minutes
            for article in article_items
            if article.reading_minutes is not None
        ]
        relevance_scores = [
            article.relevance_score
            for article in article_items
            if article.relevance_score is not None
        ]
        source_counts: dict[str, int] = {}
        for article_item in article_items:
            source = (
                article_item.article.source
                if article_item.article and article_item.article.source
                else "not available"
            )
            source_counts[source] = source_counts.get(source, 0) + 1
        return PublicationComposition(
            section_count=len(inspection.sections),
            section_titles=[section.section.heading for section in inspection.sections],
            article_count=len(article_items),
            source_counts=source_counts,
            total_reading_minutes=sum(reading_times) if reading_times else None,
            average_relevance_score=(
                round(sum(relevance_scores) / len(relevance_scores), 2)
                if relevance_scores
                else None
            ),
            missing_evaluation_count=len(article_items) - len(relevance_scores),
            missing_reading_time_count=len(article_items) - len(reading_times),
        )

    def _evidence(self, inspection: PublicationInspection) -> PublicationEvidence:
        proposal = inspection.proposal
        constraints = proposal.constraint_results if proposal else []
        penalties = [
            (constraint.name, constraint.penalty)
            for constraint in sorted(
                constraints,
                key=lambda constraint: constraint.penalty,
                reverse=True,
            )
            if constraint.penalty > 0
        ][:3]
        context = PublicationEditorialContext(
            proposal_objective_value=proposal.objective_value if proposal else None,
            satisfied_constraint_count=len(
                [constraint for constraint in constraints if constraint.satisfied]
            ),
            failed_constraint_count=len(
                [constraint for constraint in constraints if not constraint.satisfied]
            ),
            largest_penalties=penalties,
            review_decisions=[
                review.decision.value for review in inspection.proposal_reviews
            ],
            review_comments=[
                review.comments
                for review in inspection.proposal_reviews
                if review.comments
            ],
            metadata=inspection.metadata,
        )
        workflow_events = sorted(
            [
                *inspection.proposal_workflow_events,
                *inspection.publication_workflow_events,
            ],
            key=lambda event: event.created_at,
        )
        workflow = PublicationWorkflowSummary(
            events=[
                f"{event.created_at.isoformat()} {event.artefact_type} {event.event_type}"
                for event in workflow_events
            ],
            rendered_output_count=len(inspection.rendered_outputs),
        )
        return PublicationEvidence(
            summary=self._evidence_summary(inspection, context),
            workflow=workflow,
            editorial_context=context,
        )

    def _evidence_summary(
        self,
        inspection: PublicationInspection,
        context: PublicationEditorialContext,
    ) -> str:
        parts = []
        if inspection.proposal:
            parts.append(
                f"Proposal objective value {inspection.proposal.objective_value}"
            )
            parts.append(f"{context.satisfied_constraint_count} satisfied constraints")
            parts.append(f"{context.failed_constraint_count} failed constraints")
        else:
            parts.append("No originating proposal record was found")
        if context.review_decisions:
            parts.append("review decisions " + ", ".join(context.review_decisions))
        else:
            parts.append("no proposal reviews recorded")
        return "; ".join(parts) + "."

    def _editorial_summary(
        self,
        inspection: PublicationInspection,
        composition: PublicationComposition,
        evidence: PublicationEvidence,
    ) -> str:
        proposal_text = f"This publication was created from IssueProposal {inspection.publication.proposal_id}."
        selected_text = (
            f" The proposal selected {len(inspection.proposal.article_ids)} articles."
            if inspection.proposal
            else " The originating proposal record is not available."
        )
        review_text = (
            f" {len(inspection.proposal_reviews)} editorial review(s) are recorded."
        )
        publication_text = (
            f" The publication contains {composition.section_count} sections "
            f"and {composition.article_count} articles."
        )
        workflow_text = (
            f" {len(evidence.workflow.events)} workflow event(s) are recorded."
        )
        return (
            proposal_text
            + selected_text
            + review_text
            + publication_text
            + workflow_text
        )

    def _interpretation(self, composition: PublicationComposition) -> str:
        parts = [
            "This publication reflects the stored Publication artefact.",
            "It contains articles selected by the recorded publication sections.",
        ]
        if composition.source_counts:
            parts.append(
                "It includes material from "
                f"{len(composition.source_counts)} recorded sources."
            )
        return " ".join(parts)

    def _limitations(
        self,
        inspection: PublicationInspection,
        composition: PublicationComposition,
    ) -> PublicationLimitations:
        limitations: list[str] = []
        if inspection.proposal is None:
            limitations.append("Originating IssueProposal was not found.")
        if inspection.optimisation_request is None:
            limitations.append("Originating OptimisationRequest was not found.")
        if not inspection.proposal_reviews:
            limitations.append("No editorial reviews recorded.")
        if not any(review.comments for review in inspection.proposal_reviews):
            limitations.append("No review comments recorded.")
        if not inspection.rendered_outputs:
            limitations.append("No rendered outputs recorded.")
        if composition.missing_evaluation_count:
            limitations.append(
                f"{composition.missing_evaluation_count} articles have missing evaluations."
            )
        if composition.missing_reading_time_count:
            limitations.append(
                f"{composition.missing_reading_time_count} articles have missing reading-time data."
            )
        if not inspection.publication_workflow_events:
            limitations.append("No publication workflow events recorded.")
        if not limitations:
            limitations.append(
                "The explanation is limited to stored artefacts and does not "
                "recreate editorial reasoning."
            )
        return PublicationLimitations(items=limitations)

    def _related_artefacts(
        self,
        inspection: PublicationInspection,
        composition: PublicationComposition,
    ) -> dict[str, list[str]]:
        artefacts: dict[str, list[str]] = {
            "publication": [str(inspection.publication.id)],
            "proposal": [str(inspection.publication.proposal_id)],
            "article_count": [str(composition.article_count)],
        }
        if inspection.optimisation_request:
            artefacts["optimisation_request"] = [
                str(inspection.optimisation_request.id)
            ]
        if inspection.proposal_reviews:
            artefacts["reviews"] = [
                str(review.id) for review in inspection.proposal_reviews
            ]
        if inspection.rendered_outputs:
            artefacts["rendered_outputs"] = [
                output.output_path or str(output.event_id)
                for output in inspection.rendered_outputs
            ]
        return artefacts

    def _next_actions(
        self,
        inspection: PublicationInspection,
    ) -> list[NextAction]:
        publication = inspection.publication
        actions = [
            NextAction(
                label="Inspect publication",
                command=f"editorial publication show {publication.id} --db <db>",
            ),
            NextAction(
                label="Inspect proposal",
                command=f"editorial proposal show {publication.proposal_id} --db <db>",
            ),
            NextAction(
                label="Explain proposal",
                command=f"editorial explain proposal {publication.proposal_id} --db <db>",
            ),
        ]
        if inspection.optimisation_request:
            actions.append(
                NextAction(
                    label="Explain optimisation request",
                    command=(
                        "editorial explain optimisation-request "
                        f"{inspection.optimisation_request.id} --db <db>"
                    ),
                )
            )
        first_article = next(
            (
                article.article_id
                for section in inspection.sections
                for article in section.articles
            ),
            None,
        )
        if first_article:
            actions.append(
                NextAction(
                    label="Inspect first article",
                    command=f"editorial article show {first_article} --db <db>",
                )
            )
        return actions
