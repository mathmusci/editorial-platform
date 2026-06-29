from __future__ import annotations

from collections.abc import Iterable

from editorial.models import WorkflowEvent


EVENT_STATE_MAP = {
    "proposal-created": "draft",
    "review-requested": "under_review",
    "review-submitted": "reviewed",
    "proposal-approved": "approved",
    "proposal-rejected": "rejected",
    "publication-created": "published",
    "publication-published": "published",
}


class WorkflowProjection:
    def state_for(self, events: Iterable[WorkflowEvent]) -> str:
        state = "unknown"
        for event in events:
            state = EVENT_STATE_MAP.get(event.event_type, state)
        return state
