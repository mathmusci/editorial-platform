from pathlib import Path

from editorial.config import PublicationConfig
from editorial.engine import EditorialEngine
from editorial.models import OptimisationRequest
from editorial.optimisers import build_optimiser_from_request
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLiteWorkflowEventRepository,
)


def template_from_config(config: PublicationConfig, created_by: str | None = None):
    return OptimisationRequest(
        publication=config.publication.name,
        strategy=config.optimisation.strategy,
        settings=config.optimisation.settings,
        constraints=config.optimisation.constraints,
        goals={"maximise": config.optimisation.maximise},
        created_by=created_by,
    )


def run_optimisation_request(request: OptimisationRequest, db: Path):
    optimiser = build_optimiser_from_request(request)
    result = EditorialEngine(
        SQLiteArticleRepository(db),
        SQLiteExtractionRepository(db),
        SQLiteEvaluationRepository(db),
        SQLiteIssueProposalRepository(db),
        SQLiteWorkflowEventRepository(db),
    ).optimise_request(optimiser, request)
    return result, SQLiteIssueProposalRepository(db).get(result.proposal_id)


def generate_proposal(config: PublicationConfig, config_path: Path, db: Path):
    request = template_from_config(config).model_copy(
        update={"metadata": {"config": str(config_path), "source": "workspace"}}
    )
    SQLiteOptimisationRequestRepository(db).insert(request)
    return run_optimisation_request(request, db)
