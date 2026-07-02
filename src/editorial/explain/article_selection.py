from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from editorial.explain.common import NextAction, simple_payload_highlights
from editorial.models import (
    Article,
    ConstraintResult,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
)


class ArticleSelectionArticleNotFound(Exception):
    pass


class ArticleSelectionEvidence(BaseModel):
    evidence_type: Literal["extraction", "evaluation"]
    kind: str
    producer: str
    score: float | None = None
    confidence: float | None = None
    rationale: str | None = None
    highlights: dict[str, Any]


class ArticleSelectionConstraintContext(BaseModel):
    name: str
    kind: str
    satisfied: bool
    value: Any = None
    target: Any = None
    penalty: float
    interpretation: str


class ArticleSelectionOutcome(BaseModel):
    included: bool
    status: str
    explanation: str


class ArticleSelectionProposalContext(BaseModel):
    selected_article_count: int
    objective_value: float
    satisfied_constraint_count: int
    failed_constraint_count: int
    largest_penalties: list[tuple[str, float]]
    source_counts: dict[str, int]
    article_source_represented: bool | None = None


class ArticleSelectionExplanation(BaseModel):
    proposal_id: UUID
    article_id: UUID
    article_title: str
    article_source: str | None = None
    article_url: str | None = None
    optimisation_request_id: UUID | None = None
    optimiser: str
    proposal_objective_value: float
    outcome: ArticleSelectionOutcome
    evidence: list[ArticleSelectionEvidence]
    proposal_context: ArticleSelectionProposalContext
    constraint_context: list[ArticleSelectionConstraintContext]
    next_actions: list[NextAction]


class ArticleSelectionExplanationService:
    def __init__(
        self,
        proposals: SQLiteIssueProposalRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        evaluations: SQLiteEvaluationRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
    ):
        self.proposals = proposals
        self.articles = articles
        self.extractions = extractions
        self.evaluations = evaluations
        self.optimisation_requests = optimisation_requests

    def get(
        self, proposal_id: UUID, article_id: UUID
    ) -> ArticleSelectionExplanation | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None

        article = self.articles.get(article_id)
        if article is None:
            raise ArticleSelectionArticleNotFound

        extractions = self.extractions.list(article_id=article_id)
        evaluations = self.evaluations.list(article_id=article_id)
        request = self._optimisation_request_for(proposal)
        included = article_id in proposal.article_ids
        evidence = self._evidence(extractions, evaluations)

        return ArticleSelectionExplanation(
            proposal_id=proposal.id,
            article_id=article.id,
            article_title=article.title,
            article_source=article.source,
            article_url=str(article.url) if article.url else None,
            optimisation_request_id=request.id if request else None,
            optimiser=proposal.optimiser,
            proposal_objective_value=proposal.objective_value,
            outcome=self._outcome(included, evidence),
            evidence=evidence,
            proposal_context=self._proposal_context(proposal, article),
            constraint_context=self._constraint_context(proposal, request),
            next_actions=self._next_actions(proposal.id, article.id),
        )

    def _optimisation_request_for(
        self, proposal: IssueProposal
    ) -> OptimisationRequest | None:
        raw_id = proposal.metadata.get("optimisation_request_id")
        if raw_id is None:
            return None
        try:
            request_id = UUID(str(raw_id))
        except ValueError:
            return None
        return self.optimisation_requests.get(request_id)

    def _evidence(
        self, extractions: list[Extraction], evaluations: list[Evaluation]
    ) -> list[ArticleSelectionEvidence]:
        evidence: list[ArticleSelectionEvidence] = []
        for extraction in extractions:
            evidence.append(
                ArticleSelectionEvidence(
                    evidence_type="extraction",
                    kind=extraction.kind,
                    producer=extraction.extractor,
                    highlights=self._extraction_highlights(extraction),
                )
            )
        for evaluation in evaluations:
            evidence.append(
                ArticleSelectionEvidence(
                    evidence_type="evaluation",
                    kind=evaluation.kind,
                    producer=evaluation.evaluator,
                    score=evaluation.score,
                    confidence=evaluation.confidence,
                    rationale=evaluation.rationale,
                    highlights=self._evaluation_highlights(evaluation),
                )
            )
        return evidence

    def _extraction_highlights(self, extraction: Extraction) -> dict[str, Any]:
        if extraction.kind == "reading_time":
            return {
                key: extraction.payload[key]
                for key in ("reading_minutes", "word_count")
                if key in extraction.payload
            }
        if extraction.kind == "summary" and "summary" in extraction.payload:
            return {"summary": extraction.payload["summary"]}
        return simple_payload_highlights(extraction.payload)

    def _evaluation_highlights(self, evaluation: Evaluation) -> dict[str, Any]:
        highlights = {
            key: evaluation.payload[key]
            for key in ("evidence", "generated_by", "provider", "model")
            if key in evaluation.payload
        }
        if not highlights:
            highlights = simple_payload_highlights(evaluation.payload)
        return highlights

    def _outcome(
        self, included: bool, evidence: list[ArticleSelectionEvidence]
    ) -> ArticleSelectionOutcome:
        reading_time = self._reading_time(evidence)
        relevance = self._relevance(evidence)
        evidence_parts: list[str] = []
        if relevance is not None:
            evidence_parts.append(f"relevance score {relevance}")
        if reading_time is not None:
            evidence_parts.append(f"reading time {reading_time} minutes")

        if included:
            explanation = "This article was selected by the optimiser."
            if evidence_parts:
                explanation += (
                    " Stored evidence shows " + " and ".join(evidence_parts) + "."
                )
            else:
                explanation += " No extraction or evaluation evidence is available."
            return ArticleSelectionOutcome(
                included=True,
                status="This article was included in the proposal.",
                explanation=explanation,
            )

        explanation = (
            "This article was not selected by the optimiser. The stored proposal "
            "does not record the exact exclusion reason, but the available "
            "evidence is shown below."
        )
        if evidence_parts:
            explanation += (
                " Stored evidence includes " + " and ".join(evidence_parts) + "."
            )
        return ArticleSelectionOutcome(
            included=False,
            status="This article was not included in the proposal.",
            explanation=explanation,
        )

    def _reading_time(
        self, evidence: list[ArticleSelectionEvidence]
    ) -> int | float | None:
        for item in evidence:
            if item.kind == "reading_time":
                reading_minutes = item.highlights.get("reading_minutes")
                if isinstance(reading_minutes, int | float):
                    return reading_minutes
        return None

    def _relevance(self, evidence: list[ArticleSelectionEvidence]) -> float | None:
        for item in evidence:
            if item.evidence_type == "evaluation" and item.kind == "relevance":
                return item.score
        return None

    def _proposal_context(
        self, proposal: IssueProposal, article: Article
    ) -> ArticleSelectionProposalContext:
        source_counts = self._selected_source_counts(proposal)
        largest_penalties = [
            (constraint.name, constraint.penalty)
            for constraint in sorted(
                proposal.constraint_results,
                key=lambda constraint: constraint.penalty,
                reverse=True,
            )
            if constraint.penalty > 0
        ][:3]
        return ArticleSelectionProposalContext(
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
            largest_penalties=largest_penalties,
            source_counts=source_counts,
            article_source_represented=(
                source_counts.get(article.source, 0) > 0
                if article.source is not None
                else None
            ),
        )

    def _selected_source_counts(self, proposal: IssueProposal) -> dict[str, int]:
        counts: dict[str, int] = {}
        for article_id in proposal.article_ids:
            article = self.articles.get(article_id)
            source = article.source if article and article.source else "not available"
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _constraint_context(
        self,
        proposal: IssueProposal,
        request: OptimisationRequest | None,
    ) -> list[ArticleSelectionConstraintContext]:
        request_constraints = set()
        if request is not None:
            request_constraints = (
                set(request.settings)
                | set(request.constraints)
                | set(request.goals)
                | set(request.preferences)
            )
        relevant_names = {
            "max_articles",
            "reading_time_target_minutes",
            "relevance_target_score",
            "mandatory_terms",
            "source_diversity_max_per_source",
        }
        contexts = []
        for constraint in proposal.constraint_results:
            if (
                constraint.name in relevant_names
                or constraint.name in request_constraints
            ):
                contexts.append(self._constraint_context_item(constraint))
        return contexts

    def _constraint_context_item(
        self, constraint: ConstraintResult
    ) -> ArticleSelectionConstraintContext:
        return ArticleSelectionConstraintContext(
            name=constraint.name,
            kind=constraint.kind,
            satisfied=constraint.satisfied,
            value=constraint.value,
            target=constraint.target,
            penalty=constraint.penalty,
            interpretation=self._constraint_interpretation(constraint),
        )

    def _constraint_interpretation(self, constraint: ConstraintResult) -> str:
        interpretations = {
            "max_articles": (
                "This records whether the stored proposal stayed within the "
                "article-count limit."
            ),
            "reading_time_target_minutes": (
                "This records how the selected set compared with the "
                "reading-time target."
            ),
            "relevance_target_score": (
                "This records how stored relevance evidence compared with the target."
            ),
            "mandatory_terms": (
                "This records mandatory-term coverage for the selected set."
            ),
            "source_diversity_max_per_source": (
                "This records source diversity for the selected set."
            ),
        }
        if constraint.penalty:
            suffix = " A penalty was recorded for this proposal-level constraint."
        else:
            suffix = " No penalty was recorded for this proposal-level constraint."
        return (
            interpretations.get(
                constraint.name,
                "This is a stored proposal-level constraint result.",
            )
            + suffix
        )

    def _next_actions(self, proposal_id: UUID, article_id: UUID) -> list[NextAction]:
        return [
            NextAction(
                label="Inspect article",
                command=f"editorial article show {article_id} --db <db>",
            ),
            NextAction(
                label="Inspect proposal",
                command=f"editorial proposal show {proposal_id} --db <db>",
            ),
            NextAction(
                label="Explain proposal",
                command=f"editorial explain proposal {proposal_id} --db <db>",
            ),
            NextAction(
                label="List evaluations",
                command="editorial evaluation list --db <db>",
            ),
        ]
