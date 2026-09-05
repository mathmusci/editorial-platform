from pathlib import Path

from editorial.models import Review, WorkflowEvent
from editorial.storage import SQLiteReviewRepository, SQLiteWorkflowEventRepository


class ReviewSubmissionService:
    def __init__(self, db: str | Path):
        self.reviews = SQLiteReviewRepository(db)
        self.events = SQLiteWorkflowEventRepository(db)

    def submit(self, review: Review) -> Review:
        self.reviews.insert(review)
        self.events.insert(
            WorkflowEvent(
                artefact_type=review.artefact_type,
                artefact_id=review.artefact_id,
                event_type="review-submitted",
                actor=review.reviewer,
                payload={
                    "review_id": str(review.id),
                    "decision": review.decision.value,
                },
            )
        )
        return review
