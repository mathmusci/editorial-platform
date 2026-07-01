from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import (
    IssueProposal,
    OptimisationRequest,
    Publication,
    Review,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


class ReviewInspectionSummary(BaseModel):
    review_id: UUID
    created_at: datetime
    reviewer: str
    decision: str
    artefact_type: str
    artefact_id: UUID
    comments_preview: str | None = None


class ReviewInspection(BaseModel):
    review: Review
    issue_proposal: IssueProposal | None = None
    optimisation_request: OptimisationRequest | None = None
    publications: list[Publication]
    review_workflow_events: list[WorkflowEvent]
    artefact_workflow_events: list[WorkflowEvent]
    detailed_inspection_available: bool = False
    metadata: dict[str, Any]


class ReviewInspectionService:
    def __init__(
        self,
        reviews: SQLiteReviewRepository,
        proposals: SQLiteIssueProposalRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        publications: SQLitePublicationRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.reviews = reviews
        self.proposals = proposals
        self.optimisation_requests = optimisation_requests
        self.publications = publications
        self.workflow_events = workflow_events

    def list(
        self,
        artefact_type: str | None = None,
        artefact_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[ReviewInspectionSummary]:
        return [
            self._summary_for(review)
            for review in self.reviews.list(
                artefact_type=artefact_type, artefact_id=artefact_id, limit=limit
            )
        ]

    def get(self, review_id: UUID) -> ReviewInspection | None:
        review = self.reviews.get(review_id)
        if review is None:
            return None

        proposal = (
            self.proposals.get(review.artefact_id)
            if review.artefact_type == "issue_proposal"
            else None
        )
        return ReviewInspection(
            review=review,
            issue_proposal=proposal,
            optimisation_request=self._optimisation_request_for(proposal),
            publications=self._publications_for(review),
            review_workflow_events=self.workflow_events.list(
                artefact_type="review", artefact_id=review.id
            ),
            artefact_workflow_events=self.workflow_events.list(
                artefact_type=review.artefact_type,
                artefact_id=review.artefact_id,
            ),
            detailed_inspection_available=review.artefact_type == "issue_proposal",
            metadata=review.metadata,
        )

    def _summary_for(self, review: Review) -> ReviewInspectionSummary:
        return ReviewInspectionSummary(
            review_id=review.id,
            created_at=review.created_at,
            reviewer=review.reviewer,
            decision=review.decision.value,
            artefact_type=review.artefact_type,
            artefact_id=review.artefact_id,
            comments_preview=self._comments_preview(review.comments),
        )

    def _optimisation_request_for(
        self, proposal: IssueProposal | None
    ) -> OptimisationRequest | None:
        if proposal is None:
            return None
        raw_id = proposal.metadata.get("optimisation_request_id")
        if raw_id is None:
            return None
        try:
            return self.optimisation_requests.get(UUID(str(raw_id)))
        except ValueError:
            return None

    def _publications_for(self, review: Review) -> list[Publication]:
        if review.artefact_type != "issue_proposal":
            return []
        return [
            publication
            for publication in self.publications.list()
            if publication.proposal_id == review.artefact_id
        ]

    def _comments_preview(self, comments: str | None) -> str | None:
        if comments is None:
            return None
        collapsed = " ".join(comments.split())
        if len(collapsed) <= 80:
            return collapsed
        return collapsed[:77].rstrip() + "..."
