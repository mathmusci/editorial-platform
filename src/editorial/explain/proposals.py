from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from editorial.explain.common import NextAction, pluralize
from editorial.inspection import ProposalArticleInspection, ProposalInspection
from editorial.inspection.proposals import ProposalInspectionService
from editorial.models import ConstraintResult


class ConstraintExplanation(BaseModel):
    name: str
    kind: str
    satisfied: bool
    value: object | None = None
    target: object | None = None
    penalty: float
    message: str | None = None
    explanation: str


class PenaltyBreakdown(BaseModel):
    total_penalty: float
    largest_penalty_name: str | None = None
    ordered_constraints: list[ConstraintExplanation]
    zero_penalty_constraints: list[str]
    failed_constraints: list[str]
    objective_note: str | None = None


class ArticleExplanation(BaseModel):
    article_id: UUID
    title: str
    source: str | None = None
    url: str | None = None
    reading_minutes: int | float | None = None
    relevance_score: float | None = None
    relevance_rationale: str | None = None
    explanation: str


class TradeOffSummary(BaseModel):
    total_reading_minutes: int | float | None = None
    average_relevance_score: float | None = None
    source_counts: dict[str, int]
    missing_evaluation_count: int
    missing_reading_time_count: int
    summary: str


class ProposalExplanation(BaseModel):
    proposal_id: UUID
    created_at: datetime
    optimisation_request_id: UUID | None = None
    publication_name: str | None = None
    optimiser: str
    selected_article_count: int
    objective_value: float
    editorial_summary: str
    constraints: list[ConstraintExplanation]
    penalty_breakdown: PenaltyBreakdown
    articles: list[ArticleExplanation]
    trade_off_summary: TradeOffSummary
    next_actions: list[NextAction]


class ProposalExplanationService:
    def __init__(self, proposal_inspections: ProposalInspectionService):
        self.proposal_inspections = proposal_inspections

    def get(self, proposal_id: UUID) -> ProposalExplanation | None:
        inspection = self.proposal_inspections.get(proposal_id)
        if inspection is None:
            return None
        return self.build(inspection)

    def build(self, inspection: ProposalInspection) -> ProposalExplanation:
        proposal = inspection.proposal
        constraints = [
            self._constraint_explanation(constraint)
            for constraint in inspection.constraint_results
        ]
        penalty_breakdown = self._penalty_breakdown(
            constraints, proposal.objective_value
        )
        articles = [
            self._article_explanation(article)
            for article in inspection.selected_articles
        ]
        trade_off_summary = self._trade_off_summary(articles)

        return ProposalExplanation(
            proposal_id=proposal.id,
            created_at=proposal.created_at,
            optimisation_request_id=(
                inspection.optimisation_request.id
                if inspection.optimisation_request
                else None
            ),
            publication_name=inspection.publication_name,
            optimiser=proposal.optimiser,
            selected_article_count=len(proposal.article_ids),
            objective_value=proposal.objective_value,
            editorial_summary=self._editorial_summary(
                inspection, constraints, penalty_breakdown
            ),
            constraints=constraints,
            penalty_breakdown=penalty_breakdown,
            articles=articles,
            trade_off_summary=trade_off_summary,
            next_actions=self._next_actions(proposal.id),
        )

    def _constraint_explanation(
        self, constraint: ConstraintResult
    ) -> ConstraintExplanation:
        status = "satisfied" if constraint.satisfied else "not satisfied"
        parts = [f"{constraint.name} was {status}"]
        if constraint.value is not None and constraint.target is not None:
            parts.append(
                f"with value {constraint.value} against target {constraint.target}"
            )
        elif constraint.value is not None:
            parts.append(f"with value {constraint.value}")
        elif constraint.target is not None:
            parts.append(f"against target {constraint.target}")

        if constraint.penalty:
            parts.append(f"contributing a penalty of {constraint.penalty}")
        else:
            parts.append("with no penalty")

        if constraint.message:
            parts.append(f"({constraint.message})")

        return ConstraintExplanation(
            name=constraint.name,
            kind=constraint.kind,
            satisfied=constraint.satisfied,
            value=constraint.value,
            target=constraint.target,
            penalty=constraint.penalty,
            message=constraint.message,
            explanation=": ".join([parts[0], ", ".join(parts[1:])]) + ".",
        )

    def _penalty_breakdown(
        self,
        constraints: list[ConstraintExplanation],
        objective_value: float,
    ) -> PenaltyBreakdown:
        ordered = sorted(constraints, key=lambda item: item.penalty, reverse=True)
        largest = ordered[0].name if ordered else None
        objective_note = None
        if objective_value < 0 and any(item.penalty for item in constraints):
            objective_note = (
                "Objective value is negative; stored penalties may be represented "
                "against the optimiser objective."
            )
        return PenaltyBreakdown(
            total_penalty=sum(item.penalty for item in constraints),
            largest_penalty_name=largest,
            ordered_constraints=ordered,
            zero_penalty_constraints=[
                item.name for item in constraints if item.penalty == 0
            ],
            failed_constraints=[
                item.name for item in constraints if not item.satisfied
            ],
            objective_note=objective_note,
        )

    def _article_explanation(
        self, article: ProposalArticleInspection
    ) -> ArticleExplanation:
        evidence: list[str] = []
        if article.relevance_score is not None:
            evidence.append(f"relevance score {article.relevance_score}")
        if article.reading_minutes is not None:
            evidence.append(f"reading time {article.reading_minutes} minutes")

        if evidence:
            explanation = "Included with " + " and ".join(evidence) + "."
        else:
            explanation = (
                "Included in the stored proposal; no evaluation details are available."
            )

        return ArticleExplanation(
            article_id=article.article_id,
            title=article.title,
            source=article.source,
            url=article.url,
            reading_minutes=article.reading_minutes,
            relevance_score=article.relevance_score,
            relevance_rationale=article.relevance_rationale,
            explanation=explanation,
        )

    def _trade_off_summary(self, articles: list[ArticleExplanation]) -> TradeOffSummary:
        reading_times = [
            article.reading_minutes
            for article in articles
            if article.reading_minutes is not None
        ]
        relevance_scores = [
            article.relevance_score
            for article in articles
            if article.relevance_score is not None
        ]
        source_counts: dict[str, int] = {}
        for article in articles:
            source = article.source or "not available"
            source_counts[source] = source_counts.get(source, 0) + 1

        total_reading = sum(reading_times) if reading_times else None
        average_relevance = (
            round(sum(relevance_scores) / len(relevance_scores), 2)
            if relevance_scores
            else None
        )
        missing_evaluations = len(articles) - len(relevance_scores)
        missing_reading = len(articles) - len(reading_times)

        parts = [
            f"{pluralize(len(articles), 'article')} selected",
            f"{pluralize(len(source_counts), 'source')} represented",
        ]
        if total_reading is not None:
            parts.append(f"{total_reading} total reading minutes")
        if average_relevance is not None:
            parts.append(f"average relevance score {average_relevance}")
        parts.append(
            f"{pluralize(missing_evaluations, 'missing relevance evaluation')}"
        )
        parts.append(f"{pluralize(missing_reading, 'missing reading-time extraction')}")

        return TradeOffSummary(
            total_reading_minutes=total_reading,
            average_relevance_score=average_relevance,
            source_counts=source_counts,
            missing_evaluation_count=missing_evaluations,
            missing_reading_time_count=missing_reading,
            summary="; ".join(parts) + ".",
        )

    def _editorial_summary(
        self,
        inspection: ProposalInspection,
        constraints: list[ConstraintExplanation],
        penalty_breakdown: PenaltyBreakdown,
    ) -> str:
        proposal = inspection.proposal
        publication = inspection.publication_name or "the publication"
        satisfied = len(
            [constraint for constraint in constraints if constraint.satisfied]
        )
        total = len(constraints)
        if penalty_breakdown.ordered_constraints:
            penalised = [
                constraint.name
                for constraint in penalty_breakdown.ordered_constraints
                if constraint.penalty > 0
            ]
            penalty_text = (
                "The largest penalties are " + ", ".join(penalised[:3]) + "."
                if penalised
                else "No penalties were recorded."
            )
        else:
            penalty_text = "No constraint results were recorded."

        return (
            "This proposal selected "
            f"{pluralize(len(proposal.article_ids), 'article')} for {publication}. "
            f"It was created using the {proposal.optimiser} optimiser. "
            f"The proposal satisfies {satisfied} of {total} recorded constraints. "
            f"{penalty_text}"
        )

    def _next_actions(self, proposal_id: UUID) -> list[NextAction]:
        return [
            NextAction(
                label="Inspect proposal",
                command=f"editorial proposal show {proposal_id} --db <db>",
            ),
            NextAction(
                label="Record review",
                command=(
                    "editorial review create --artefact-type issue_proposal "
                    f"--artefact-id {proposal_id} --reviewer <name> "
                    "--decision approve --db <db>"
                ),
            ),
            NextAction(
                label="Create publication",
                command=(
                    f"editorial publication create --proposal-id {proposal_id} "
                    '--title "<title>" --db <db>'
                ),
            ),
        ]
