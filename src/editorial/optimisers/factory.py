from __future__ import annotations

from editorial.config.models import OptimisationConfig
from editorial.interfaces import Optimiser
from editorial.models import OptimisationRequest
from editorial.optimisers.greedy import GreedyOptimiser


def build_optimiser(config: OptimisationConfig) -> Optimiser:
    if config.strategy == "greedy":
        return GreedyOptimiser(**config.settings)
    raise ValueError(f"Unsupported optimisation strategy: {config.strategy!r}")


def build_optimiser_from_request(request: OptimisationRequest) -> Optimiser:
    if request.strategy == "greedy":
        return GreedyOptimiser(**request.settings)
    raise ValueError(f"Unsupported optimisation strategy: {request.strategy!r}")
