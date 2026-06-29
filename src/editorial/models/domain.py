from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EditorialStatus(StrEnum):
    NEW = "new"
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_CHANGES = "needs_changes"
    COMMENT = "comment"


class Article(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    url: HttpUrl | None = None
    source: str | None = None
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    summary: str | None = None
    content: str | None = None
    status: EditorialStatus = EditorialStatus.NEW
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Extraction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    extractor: str
    extractor_version: str | None = None
    kind: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


class Evaluation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    evaluator: str
    evaluator_version: str | None = None
    kind: str
    criterion: str | None = None
    score: float | None = None
    confidence: float | None = None
    rationale: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Decision(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    article_id: UUID | None = None
    issue_id: UUID | None = None
    decision_type: str
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Issue(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    article_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class PublicationSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str = Field(min_length=1)
    article_ids: list[UUID] = Field(default_factory=list)
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Publication(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    title: str = Field(min_length=1)
    subtitle: str | None = None
    sections: list[PublicationSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class WorkflowEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    artefact_type: str = Field(min_length=1)
    artefact_id: UUID
    event_type: str = Field(min_length=1)
    actor: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
