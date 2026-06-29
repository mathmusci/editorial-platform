from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from editorial.models.common import utc_now


class WorkflowEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    artefact_type: str = Field(min_length=1)
    artefact_id: UUID
    event_type: str = Field(min_length=1)
    actor: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
