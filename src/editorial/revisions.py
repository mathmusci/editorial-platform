from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import OptimisationRequest, Review, ReviewDecision, WorkflowEvent
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


class ReviewRevision(BaseModel):
    review: Review
    source_proposal_id: UUID
    source_request_id: UUID | None = None
    request: OptimisationRequest


class ReviewRevisionService:
    def __init__(
        self,
        reviews: SQLiteReviewRepository,
        proposals: SQLiteIssueProposalRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.reviews = reviews
        self.proposals = proposals
        self.optimisation_requests = optimisation_requests
        self.workflow_events = workflow_events

    def create(
        self,
        review_id: UUID,
        template: OptimisationRequest,
        *,
        created_by: str | None = None,
        settings: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        goals: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> ReviewRevision:
        review = self.reviews.get(review_id)
        if review is None:
            raise ValueError(f"Review not found: {review_id}")
        if review.artefact_type != "issue_proposal":
            raise ValueError(
                "A revision request can only be created from an issue_proposal review"
            )
        if review.decision != ReviewDecision.NEEDS_CHANGES:
            raise ValueError(
                "A revision request requires a needs_changes review decision"
            )

        proposal = self.proposals.get(review.artefact_id)
        if proposal is None:
            raise ValueError(f"Issue proposal not found: {review.artefact_id}")
        source_request_id = self._source_request_id(proposal.metadata)
        actor = created_by or template.created_by or review.reviewer
        request = OptimisationRequest(
            publication=template.publication,
            strategy=template.strategy,
            settings={**template.settings, **(settings or {})},
            constraints={**template.constraints, **(constraints or {})},
            goals={**template.goals, **(goals or {})},
            preferences={**template.preferences, **(preferences or {})},
            created_by=actor,
            parent_request_id=source_request_id,
            parent_proposal_id=proposal.id,
            metadata={
                **template.metadata,
                "source": "editorial review revise",
                "source_review_id": str(review.id),
                "source_review_decision": review.decision.value,
                "source_reviewer": review.reviewer,
                "review_comments": review.comments,
                "review_findings": review.findings,
                "review_recommendations": review.recommendations,
            },
        )
        self.optimisation_requests.insert(request)
        self._record_events(review, request, proposal.id, source_request_id, actor)
        return ReviewRevision(
            review=review,
            source_proposal_id=proposal.id,
            source_request_id=source_request_id,
            request=request,
        )

    def _source_request_id(self, metadata: dict[str, Any]) -> UUID | None:
        value = metadata.get("optimisation_request_id")
        if value is None:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None

    def _record_events(
        self,
        review: Review,
        request: OptimisationRequest,
        proposal_id: UUID,
        source_request_id: UUID | None,
        actor: str,
    ) -> None:
        payload = {
            "review_id": str(review.id),
            "revision_request_id": str(request.id),
            "source_proposal_id": str(proposal_id),
            "source_request_id": (
                str(source_request_id) if source_request_id is not None else None
            ),
        }
        self.workflow_events.insert(
            WorkflowEvent(
                artefact_type="issue_proposal",
                artefact_id=proposal_id,
                event_type="revision-requested",
                actor=actor,
                reason=review.comments,
                payload=payload,
            )
        )
        self.workflow_events.insert(
            WorkflowEvent(
                artefact_type="review",
                artefact_id=review.id,
                event_type="revision-request-created",
                actor=actor,
                reason="Created from needs_changes review",
                payload=payload,
            )
        )
        self.workflow_events.insert(
            WorkflowEvent(
                artefact_type="optimisation_request",
                artefact_id=request.id,
                event_type="optimisation-request-created",
                actor=actor,
                reason="Created as a proposal revision request",
                payload=payload,
            )
        )
