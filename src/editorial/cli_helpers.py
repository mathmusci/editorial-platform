from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import typer

from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.models import OptimisationRequest, Publication, Review, WorkflowEvent
from editorial.optimisers import build_optimiser_from_request
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteWorkflowEventRepository,
)


def parse_payload(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("payload must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter("payload must be a JSON object")
    return parsed


def parse_key_values(values: list[str] | None, option_name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise typer.BadParameter(f"{option_name} must use key=value")
        key, raw = value.split("=", 1)
        if not key:
            raise typer.BadParameter(f"{option_name} key cannot be empty")
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            parsed[key] = raw
    return parsed


def request_from_config(
    config: Path,
    created_by: str | None = None,
    parent_request_id: UUID | None = None,
    parent_proposal_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> OptimisationRequest:
    cfg = load_publication_config(config)
    return OptimisationRequest(
        publication=cfg.publication.name,
        strategy=cfg.optimisation.strategy,
        settings=cfg.optimisation.settings,
        constraints=cfg.optimisation.constraints,
        goals={"maximise": cfg.optimisation.maximise},
        created_by=created_by,
        parent_request_id=parent_request_id,
        parent_proposal_id=parent_proposal_id,
        metadata={"config": str(config), **(metadata or {})},
    )


def run_optimisation_request(
    request: OptimisationRequest, db: Path
) -> tuple[object, object]:
    optimiser = build_optimiser_from_request(request)
    result = EditorialEngine(
        SQLiteArticleRepository(db),
        SQLiteExtractionRepository(db),
        SQLiteEvaluationRepository(db),
        SQLiteIssueProposalRepository(db),
        SQLiteWorkflowEventRepository(db),
    ).optimise_request(optimiser, request)
    proposal = SQLiteIssueProposalRepository(db).get(result.proposal_id)
    return result, proposal


def record_review_submitted(review: Review, db: Path) -> None:
    SQLiteWorkflowEventRepository(db).insert(
        WorkflowEvent(
            artefact_type=review.artefact_type,
            artefact_id=review.artefact_id,
            event_type="review-submitted",
            actor=review.reviewer,
            payload={
                "review_id": str(review.id),
                "decision": review.decision.value,
            },
        )
    )


def record_publication_created(publication: Publication, db: Path) -> None:
    SQLiteWorkflowEventRepository(db).insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-created",
            payload={"proposal_id": str(publication.proposal_id)},
        )
    )


def record_publication_rendered(
    publication: Publication, output_path: Path, db: Path
) -> None:
    SQLiteWorkflowEventRepository(db).insert(
        WorkflowEvent(
            artefact_type="publication",
            artefact_id=publication.id,
            event_type="publication-published",
            payload={"format": "markdown", "output_path": str(output_path)},
        )
    )
