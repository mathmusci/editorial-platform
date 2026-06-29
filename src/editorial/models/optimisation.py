from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from editorial.models.common import utc_now


class ConstraintResult(BaseModel):
    name: str
    kind: Literal["hard", "soft", "goal"]
    satisfied: bool
    value: Any = None
    target: Any = None
    penalty: float = 0.0
    message: str | None = None


class IssueProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    optimiser: str
    optimiser_version: str | None = None
    article_ids: list[UUID] = Field(default_factory=list)
    objective_value: float
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class OptimisationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    publication: str | None = None
    strategy: str = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    goals: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    parent_request_id: UUID | None = None
    parent_proposal_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
