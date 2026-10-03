from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from editorial.models import Article, Evaluation, Extraction, IssueProposal
from editorial.optimisers.greedy import GreedyOptimiser


class MilpOptimiser(GreedyOptimiser):
    name = "milp"
    version = "0.1.0"

    def __init__(self, **settings: object) -> None:
        super().__init__(**settings)
        if self.max_articles < 0:
            raise ValueError("max_articles must be zero or greater")
        for name in (
            "relevance_target_weight",
            "reading_time_weight",
            "mandatory_terms_weight",
            "source_diversity_weight",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be zero or greater for MILP")

    def optimise(
        self,
        articles: list[Article],
        extractions: list[Extraction],
        evaluations: list[Evaluation],
    ) -> IssueProposal:
        candidates = self._candidates(articles, extractions, evaluations)
        if not candidates or self.max_articles == 0:
            return self._proposal(candidates, [])

        count = len(candidates)
        terms = list(dict.fromkeys(self.mandatory_terms))
        term_indices = {term: count + index for index, term in enumerate(terms)}
        deviation_index = (
            count + len(terms) if self.reading_time_target_minutes is not None else None
        )
        next_index = count + len(terms) + (deviation_index is not None)

        by_source: dict[str, list[int]] = defaultdict(list)
        for index, candidate in enumerate(candidates):
            by_source[candidate.article.source or ""].append(index)
        source_indices = (
            {source: next_index + index for index, source in enumerate(by_source)}
            if self.source_diversity_max_per_source is not None
            else {}
        )
        size = next_index + len(source_indices)

        objective = np.zeros(size)
        for index, candidate in enumerate(candidates):
            shortfall = (
                max(0.0, self.relevance_target_score - candidate.relevance_score)
                if self.relevance_target_score is not None
                else 0.0
            )
            objective[index] = (
                -candidate.relevance_score + self.relevance_target_weight * shortfall
            )
        for index in term_indices.values():
            objective[index] = -self.mandatory_terms_weight
        if deviation_index is not None:
            objective[deviation_index] = self.reading_time_weight
        for index in source_indices.values():
            objective[index] = self.source_diversity_weight

        rows: list[dict[int, float]] = []
        upper: list[float] = []

        def at_most(coefficients: dict[int, float], bound: float) -> None:
            rows.append(coefficients)
            upper.append(bound)

        at_most({index: 1.0 for index in range(count)}, self.max_articles)

        # A rewarded term can be selected only if at least one selected article covers it.
        for term, term_index in term_indices.items():
            covering = [
                index
                for index, candidate in enumerate(candidates)
                if term in candidate.mandatory_terms
            ]
            at_most(
                {term_index: 1.0, **{index: -1.0 for index in covering}},
                0.0,
            )

        if deviation_index is not None:
            target = float(self.reading_time_target_minutes)
            at_most(
                {
                    **{
                        index: candidate.reading_minutes
                        for index, candidate in enumerate(candidates)
                    },
                    deviation_index: -1.0,
                },
                target,
            )
            at_most(
                {
                    **{
                        index: -candidate.reading_minutes
                        for index, candidate in enumerate(candidates)
                    },
                    deviation_index: -1.0,
                },
                -target,
            )

        for source, excess_index in source_indices.items():
            at_most(
                {
                    **{index: 1.0 for index in by_source[source]},
                    excess_index: -1.0,
                },
                float(self.source_diversity_max_per_source),
            )

        row_indices = []
        column_indices = []
        values = []
        for row_index, row in enumerate(rows):
            for column_index, value in row.items():
                row_indices.append(row_index)
                column_indices.append(column_index)
                values.append(value)
        matrix = coo_matrix(
            (values, (row_indices, column_indices)), shape=(len(rows), size)
        ).tocsc()
        lower_bounds = np.zeros(size)
        upper_bounds = np.full(size, np.inf)
        upper_bounds[: count + len(terms)] = 1
        integrality = np.zeros(size, dtype=int)
        integrality[: count + len(terms)] = 1

        result = milp(
            objective,
            integrality=integrality,
            bounds=Bounds(lower_bounds, upper_bounds),
            constraints=LinearConstraint(matrix, -np.inf, upper),
        )
        if result.status != 0 or result.x is None:
            raise RuntimeError(
                f"MILP optimiser did not find an optimal solution: {result.message}"
            )

        selected = [
            candidate
            for index, candidate in enumerate(candidates)
            if result.x[index] > 0.5
        ]
        proposal = self._proposal(candidates, selected)
        if abs(self._objective(selected) + result.fun) > 1e-4:
            raise RuntimeError("MILP solution does not match the configured objective")
        proposal.metadata["solver"] = "HiGHS"
        proposal.metadata["solver_status"] = "optimal"
        return proposal
