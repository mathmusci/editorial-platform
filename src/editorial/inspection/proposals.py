from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import (
    ConstraintResult,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
    Review,
    WorkflowEvent,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteOptimisationRequestRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


class ProposalArticleInspection(BaseModel):
    article_id: UUID
    title: str
    source: str | None = None
    url: str | None = None
    reading_minutes: int | float | None = None
    relevance_score: float | None = None
    relevance_rationale: str | None = None
    missing: bool = False


class ProposalInspectionSummary(BaseModel):
    proposal_id: UUID
    created_at: datetime
    optimisation_request_id: UUID | None = None
    selected_article_count: int
    objective_value: float
    publication_name: str | None = None
    review_count: int = 0
    publication_count: int = 0


class ProposalInspection(BaseModel):
    proposal: IssueProposal
    optimisation_request: OptimisationRequest | None = None
    publication_name: str | None = None
    selected_articles: list[ProposalArticleInspection]
    workflow_events: list[WorkflowEvent]
    reviews: list[Review]
    publications: list[Publication]
    constraint_results: list[ConstraintResult]
    metadata: dict[str, Any]


class ProposalInspectionService:
    def __init__(
        self,
        proposals: SQLiteIssueProposalRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        evaluations: SQLiteEvaluationRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        workflow_events: SQLiteWorkflowEventRepository,
        reviews: SQLiteReviewRepository,
        publications: SQLitePublicationRepository,
    ):
        self.proposals = proposals
        self.articles = articles
        self.extractions = extractions
        self.evaluations = evaluations
        self.optimisation_requests = optimisation_requests
        self.workflow_events = workflow_events
        self.reviews = reviews
        self.publications = publications

    def list(self, limit: int | None = None) -> list[ProposalInspectionSummary]:
        return [self._summary_for(proposal) for proposal in self.proposals.list(limit)]

    def get(self, proposal_id: UUID) -> ProposalInspection | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None

        optimisation_request = self._optimisation_request_for(proposal)
        publications = self._publications_for(proposal.id)
        return ProposalInspection(
            proposal=proposal,
            optimisation_request=optimisation_request,
            publication_name=self._publication_name(optimisation_request, publications),
            selected_articles=self._selected_articles_for(proposal),
            workflow_events=self.workflow_events.list(
                artefact_type="issue_proposal", artefact_id=proposal.id
            ),
            reviews=self.reviews.list(
                artefact_type="issue_proposal", artefact_id=proposal.id
            ),
            publications=publications,
            constraint_results=proposal.constraint_results,
            metadata=proposal.metadata,
        )

    def _summary_for(self, proposal: IssueProposal) -> ProposalInspectionSummary:
        optimisation_request = self._optimisation_request_for(proposal)
        publications = self._publications_for(proposal.id)
        reviews = self.reviews.list(
            artefact_type="issue_proposal", artefact_id=proposal.id
        )
        return ProposalInspectionSummary(
            proposal_id=proposal.id,
            created_at=proposal.created_at,
            optimisation_request_id=self._optimisation_request_id_for(proposal),
            selected_article_count=len(proposal.article_ids),
            objective_value=proposal.objective_value,
            publication_name=self._publication_name(optimisation_request, publications),
            review_count=len(reviews),
            publication_count=len(publications),
        )

    def _selected_articles_for(
        self, proposal: IssueProposal
    ) -> list[ProposalArticleInspection]:
        inspections: list[ProposalArticleInspection] = []
        for article_id in proposal.article_ids:
            article = self.articles.get(article_id)
            if article is None:
                inspections.append(
                    ProposalArticleInspection(
                        article_id=article_id,
                        title="Missing article",
                        missing=True,
                    )
                )
                continue

            extractions = self.extractions.list(article_id=article_id)
            evaluations = self.evaluations.list(article_id=article_id)
            reading_time = self._reading_minutes(extractions)
            relevance = self._relevance_evaluation(evaluations)
            inspections.append(
                ProposalArticleInspection(
                    article_id=article.id,
                    title=article.title,
                    source=article.source,
                    url=str(article.url) if article.url else None,
                    reading_minutes=reading_time,
                    relevance_score=relevance.score if relevance else None,
                    relevance_rationale=relevance.rationale if relevance else None,
                )
            )
        return inspections

    def _optimisation_request_for(
        self, proposal: IssueProposal
    ) -> OptimisationRequest | None:
        request_id = self._optimisation_request_id_for(proposal)
        if request_id is None:
            return None
        return self.optimisation_requests.get(request_id)

    def _optimisation_request_id_for(self, proposal: IssueProposal) -> UUID | None:
        raw_id = proposal.metadata.get("optimisation_request_id")
        if raw_id is None:
            return None
        try:
            return UUID(str(raw_id))
        except ValueError:
            return None

    def _publications_for(self, proposal_id: UUID) -> list[Publication]:
        return [
            publication
            for publication in self.publications.list()
            if publication.proposal_id == proposal_id
        ]

    def _publication_name(
        self,
        optimisation_request: OptimisationRequest | None,
        publications: list[Publication],
    ) -> str | None:
        if optimisation_request and optimisation_request.publication:
            return optimisation_request.publication
        if publications:
            return publications[0].title
        return None

    def _reading_minutes(self, extractions: list[Extraction]) -> int | float | None:
        for extraction in extractions:
            if extraction.kind == "reading_time":
                reading_minutes = extraction.payload.get("reading_minutes")
                if isinstance(reading_minutes, int | float):
                    return reading_minutes
        return None

    def _relevance_evaluation(self, evaluations: list[Evaluation]) -> Evaluation | None:
        for evaluation in evaluations:
            if evaluation.kind == "relevance":
                return evaluation
        return None
