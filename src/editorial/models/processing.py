from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from editorial.models.common import utc_now

ProcessingKind = Literal["ingest", "extract", "evaluate"]
ProcessingStatus = Literal["queued", "running", "completed", "failed", "interrupted"]


class ProcessingRunOptions(BaseModel):
    limit: int | None = Field(default=None, gt=0)
    offset: int = Field(default=0, ge=0)
    article_ids: list[UUID] = Field(default_factory=list)
    missing_only: bool = False
    force: bool = False

    @model_validator(mode="after")
    def validate_resume_mode(self) -> ProcessingRunOptions:
        if self.missing_only and self.force:
            raise ValueError("missing_only and force cannot be used together")
        return self


class ProcessingRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: ProcessingKind
    status: ProcessingStatus = "queued"
    publication_name: str
    config_path: str
    database_path: str
    config_digest: str
    options: ProcessingRunOptions = Field(default_factory=ProcessingRunOptions)
    article_count: int = 0
    processor_count: int = 0
    total_operations: int = 0
    completed_operations: int = 0
    stored_operations: int = 0
    skipped_operations: int = 0
    failed_operations: int = 0
    current_article_id: UUID | None = None
    current_article_title: str | None = None
    current_processor: str | None = None
    current_provider: str | None = None
    current_model: str | None = None
    error_message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def active(self) -> bool:
        return self.status in {"queued", "running"}

    @property
    def progress_percent(self) -> float:
        if self.total_operations == 0:
            return 100.0 if self.status == "completed" else 0.0
        return round(self.completed_operations / self.total_operations * 100, 1)
