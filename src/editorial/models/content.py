from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl

from editorial.models.common import utc_now


class EditorialStatus(StrEnum):
    NEW = "new"
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PUBLISHED = "published"


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
