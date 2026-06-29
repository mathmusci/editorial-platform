from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from editorial.models.common import utc_now


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
