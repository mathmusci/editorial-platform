from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from editorial.models.common import utc_now


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_CHANGES = "needs_changes"
    COMMENT = "comment"


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    artefact_type: str = Field(min_length=1)
    artefact_id: UUID
    reviewer: str = Field(min_length=1)
    decision: ReviewDecision
    comments: str | None = None
    findings: dict[str, Any] = Field(default_factory=dict)
    recommendations: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
