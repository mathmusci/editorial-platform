from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from editorial.models.common import utc_now


class PublicationArticle(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: UUID
    title: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    source: str | None = None
    url: str | None = None
    summary_extraction_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublicationSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str = Field(min_length=1)
    introduction: str | None = None
    articles: list[PublicationArticle] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        migrated = dict(value)
        if "introduction" not in migrated and "summary" in migrated:
            migrated["introduction"] = migrated.pop("summary")
        if "articles" not in migrated and "article_ids" in migrated:
            migrated["articles"] = [
                {"article_id": article_id}
                for article_id in migrated.pop("article_ids") or []
            ]
        return migrated

    @property
    def article_ids(self) -> list[UUID]:
        return [article.article_id for article in self.articles]

    @property
    def summary(self) -> str | None:
        """Backward-compatible name for a section introduction."""
        return self.introduction


class PublicationExclusion(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: UUID
    reason: str = Field(min_length=1)


class Publication(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    title: str = Field(min_length=1)
    subtitle: str | None = None
    introduction: str | None = None
    approved_review_id: UUID | None = None
    parent_publication_id: UUID | None = None
    created_by: str | None = None
    sections: list[PublicationSection] = Field(default_factory=list)
    exclusions: list[PublicationExclusion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
