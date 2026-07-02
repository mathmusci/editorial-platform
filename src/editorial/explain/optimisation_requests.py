from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import IssueProposal, OptimisationRequest
from editorial.storage import (
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
)


SETTING_EXPLANATIONS = {
    "max_articles": "Maximum number of articles the optimiser should select.",
    "reading_time_target_minutes": "Target total reading time for selected content.",
    "reading_time_weight": "Penalty weight applied to reading-time fit.",
    "relevance_target_score": "Target relevance score for selected articles.",
    "relevance_target_weight": "Penalty weight applied to relevance fit.",
    "mandatory_terms": "Terms the optimiser should try to represent.",
    "mandatory_terms_weight": "Penalty weight applied to mandatory-term coverage.",
    "source_diversity_max_per_source": "Maximum selected articles per source.",
    "source_diversity_weight": "Penalty weight applied to source diversity.",
}


class OptimisationSettingExplanation(BaseModel):
    name: str
    value: Any
    explanation: str


class LinkedProposalExplanation(BaseModel):
    proposal_id: UUID
    created_at: datetime
    optimiser: str
    selected_article_count: int
    objective_value: float
    satisfied_constraint_count: int
    failed_constraint_count: int
    total_penalty: float
    largest_penalty_name: str | None = None
    ordered_penalties: list[tuple[str, float]]


class OptimisationBalanceExplanation(BaseModel):
    items: list[str]
    summary: str


class OptimisationOutcomeExplanation(BaseModel):
    summary: str
    proposal_count: int


class NextAction(BaseModel):
    label: str
    command: str


class OptimisationRequestExplanation(BaseModel):
    request_id: UUID
    created_at: datetime
    publication: str | None = None
    strategy: str
    created_by: str | None = None
    settings: list[OptimisationSettingExplanation]
    constraints: dict[str, Any]
    goals: dict[str, Any]
    preferences: dict[str, Any]
    editorial_summary: str
    linked_proposals: list[LinkedProposalExplanation]
    balance: OptimisationBalanceExplanation
    outcome: OptimisationOutcomeExplanation
    next_actions: list[NextAction]


class OptimisationRequestExplanationService:
    def __init__(
        self,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        proposals: SQLiteIssueProposalRepository,
    ):
        self.optimisation_requests = optimisation_requests
        self.proposals = proposals

    def get(self, request_id: UUID) -> OptimisationRequestExplanation | None:
        request = self.optimisation_requests.get(request_id)
        if request is None:
            return None

        linked_proposals = self._linked_proposals(request.id)
        proposal_explanations = [
            self._proposal_explanation(proposal) for proposal in linked_proposals
        ]
        settings = [
            self._setting_explanation(name, value)
            for name, value in sorted(request.settings.items())
        ]
        balance = self._balance_explanation(request.settings)
        outcome = self._outcome_explanation(proposal_explanations)

        return OptimisationRequestExplanation(
            request_id=request.id,
            created_at=request.created_at,
            publication=request.publication,
            strategy=request.strategy,
            created_by=request.created_by,
            settings=settings,
            constraints=request.constraints,
            goals=request.goals,
            preferences=request.preferences,
            editorial_summary=self._editorial_summary(
                request, settings, proposal_explanations
            ),
            linked_proposals=proposal_explanations,
            balance=balance,
            outcome=outcome,
            next_actions=self._next_actions(request.id, proposal_explanations),
        )

    def _linked_proposals(self, request_id: UUID) -> list[IssueProposal]:
        return [
            proposal
            for proposal in self.proposals.list()
            if proposal.metadata.get("optimisation_request_id") == str(request_id)
        ]

    def _setting_explanation(
        self, name: str, value: Any
    ) -> OptimisationSettingExplanation:
        return OptimisationSettingExplanation(
            name=name,
            value=value,
            explanation=SETTING_EXPLANATIONS.get(
                name, "Custom setting recorded for this optimisation request."
            ),
        )

    def _proposal_explanation(
        self, proposal: IssueProposal
    ) -> LinkedProposalExplanation:
        ordered = sorted(
            proposal.constraint_results,
            key=lambda constraint: constraint.penalty,
            reverse=True,
        )
        return LinkedProposalExplanation(
            proposal_id=proposal.id,
            created_at=proposal.created_at,
            optimiser=proposal.optimiser,
            selected_article_count=len(proposal.article_ids),
            objective_value=proposal.objective_value,
            satisfied_constraint_count=len(
                [
                    constraint
                    for constraint in proposal.constraint_results
                    if constraint.satisfied
                ]
            ),
            failed_constraint_count=len(
                [
                    constraint
                    for constraint in proposal.constraint_results
                    if not constraint.satisfied
                ]
            ),
            total_penalty=sum(
                constraint.penalty for constraint in proposal.constraint_results
            ),
            largest_penalty_name=ordered[0].name if ordered else None,
            ordered_penalties=[
                (constraint.name, constraint.penalty) for constraint in ordered
            ],
        )

    def _balance_explanation(
        self, settings: dict[str, Any]
    ) -> OptimisationBalanceExplanation:
        items: list[str] = []
        if "max_articles" in settings:
            items.append(f"article count limit {settings['max_articles']}")
        if "reading_time_target_minutes" in settings:
            items.append(
                f"reading-time target {settings['reading_time_target_minutes']} minutes"
            )
        if "relevance_target_score" in settings:
            items.append(f"relevance target {settings['relevance_target_score']}")
        if "mandatory_terms" in settings:
            items.append(f"mandatory terms {settings['mandatory_terms']}")
        if "source_diversity_max_per_source" in settings:
            items.append(
                "source diversity limit "
                f"{settings['source_diversity_max_per_source']} per source"
            )

        summary = (
            "The optimiser was asked to balance " + "; ".join(items) + "."
            if items
            else "No recognised balance settings were recorded."
        )
        return OptimisationBalanceExplanation(items=items, summary=summary)

    def _outcome_explanation(
        self, proposals: list[LinkedProposalExplanation]
    ) -> OptimisationOutcomeExplanation:
        if not proposals:
            return OptimisationOutcomeExplanation(
                summary="No IssueProposal linked to this optimisation request was found.",
                proposal_count=0,
            )

        if len(proposals) == 1:
            proposal = proposals[0]
            largest = proposal.largest_penalty_name or "none"
            summary = (
                f"The linked proposal selected {proposal.selected_article_count} "
                f"articles. It satisfied {proposal.satisfied_constraint_count} "
                f"of {proposal.satisfied_constraint_count + proposal.failed_constraint_count} "
                f"recorded constraints. The largest recorded penalty was {largest}."
            )
        else:
            summary = (
                f"{len(proposals)} proposals were linked to this optimisation request. "
                "Recorded proposal results are shown without claiming one is optimal."
            )
        return OptimisationOutcomeExplanation(
            summary=summary,
            proposal_count=len(proposals),
        )

    def _editorial_summary(
        self,
        request: OptimisationRequest,
        settings: list[OptimisationSettingExplanation],
        proposals: list[LinkedProposalExplanation],
    ) -> str:
        publication = request.publication or "the publication"
        setting_names = [setting.name for setting in settings]
        setting_text = (
            " It used settings for " + ", ".join(setting_names) + "."
            if setting_names
            else " No settings were recorded."
        )
        proposal_text = (
            f" {len(proposals)} proposal was produced."
            if len(proposals) == 1
            else f" {len(proposals)} proposals were produced."
        )
        return (
            f"This optimisation request asked the {request.strategy} optimiser "
            f"to construct a proposal for {publication}."
            f"{setting_text}{proposal_text}"
        )

    def _next_actions(
        self,
        request_id: UUID,
        proposals: list[LinkedProposalExplanation],
    ) -> list[NextAction]:
        actions = [
            NextAction(
                label="Inspect optimisation request",
                command=(f"editorial optimisation-request show {request_id} --db <db>"),
            ),
            NextAction(
                label="List proposals",
                command="editorial proposal list --db <db>",
            ),
        ]
        for proposal in proposals:
            actions.append(
                NextAction(
                    label="Inspect linked proposal",
                    command=f"editorial proposal show {proposal.proposal_id} --db <db>",
                )
            )
            actions.append(
                NextAction(
                    label="Explain linked proposal",
                    command=(
                        f"editorial explain proposal {proposal.proposal_id} --db <db>"
                    ),
                )
            )
        return actions
