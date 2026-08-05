from __future__ import annotations
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


class PublicationIdentity(BaseModel):
    name: str
    description: str | None = None


class ProcessorConfig(BaseModel):
    type: str
    key: str | None = Field(
        default=None,
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    name: str | None = None
    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class EditorialPolicyConfig(BaseModel):
    maximum_age_days: int | None = None
    maximum_articles: int | None = None
    maximum_reading_minutes: int | None = None
    statuses_eligible_for_issue: list[str] = Field(default_factory=lambda: ["accepted"])


class OptimisationConfig(BaseModel):
    strategy: str = "none"
    settings: dict[str, Any] = Field(default_factory=dict)
    maximise: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class PublicationConfig(BaseModel):
    publication: PublicationIdentity
    providers: list[ProcessorConfig] = Field(default_factory=list)
    extractors: list[ProcessorConfig] = Field(default_factory=list)
    evaluators: list[ProcessorConfig] = Field(default_factory=list)
    editorial_policy: EditorialPolicyConfig = Field(
        default_factory=EditorialPolicyConfig
    )
    optimisation: OptimisationConfig = Field(default_factory=OptimisationConfig)
    publishers: list[ProcessorConfig] = Field(default_factory=list)
    base_path: Path | None = None
