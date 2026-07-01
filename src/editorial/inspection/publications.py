from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from editorial.models import (
    Article,
    Evaluation,
    IssueProposal,
    OptimisationRequest,
    Publication,
    PublicationSection,
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


class PublicationInspectionSummary(BaseModel):
    publication_id: UUID
    created_at: datetime
    title: str
    subtitle: str | None = None
    proposal_id: UUID
    section_count: int
    article_count: int
    rendered_output_count: int = 0
    status: str | None = None


class PublicationArticleInspection(BaseModel):
    article: Article | None
    article_id: UUID
    reading_minutes: int | float | None = None
    relevance_score: float | None = None
    relevance_rationale: str | None = None


class PublicationSectionInspection(BaseModel):
    section: PublicationSection
    order: int
    articles: list[PublicationArticleInspection]


class RenderedOutputInspection(BaseModel):
    event_id: UUID
    format: str | None = None
    output_path: str | None = None
    created_at: datetime


class PublicationInspection(BaseModel):
    publication: Publication
    proposal: IssueProposal | None = None
    optimisation_request: OptimisationRequest | None = None
    sections: list[PublicationSectionInspection]
    proposal_reviews: list[Review]
    publication_workflow_events: list[WorkflowEvent]
    proposal_workflow_events: list[WorkflowEvent]
    rendered_outputs: list[RenderedOutputInspection]
    metadata: dict[str, Any]


class PublicationInspectionService:
    def __init__(
        self,
        publications: SQLitePublicationRepository,
        proposals: SQLiteIssueProposalRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        evaluations: SQLiteEvaluationRepository,
        reviews: SQLiteReviewRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.publications = publications
        self.proposals = proposals
        self.optimisation_requests = optimisation_requests
        self.articles = articles
        self.extractions = extractions
        self.evaluations = evaluations
        self.reviews = reviews
        self.workflow_events = workflow_events

    def list(self, limit: int | None = None) -> list[PublicationInspectionSummary]:
        return [
            self._summary_for(publication)
            for publication in self.publications.list(limit=limit)
        ]

    def get(self, publication_id: UUID) -> PublicationInspection | None:
        publication = self.publications.get(publication_id)
        if publication is None:
            return None

        proposal = self.proposals.get(publication.proposal_id)
        optimisation_request = self._optimisation_request_for(proposal)
        publication_events = self.workflow_events.list(
            artefact_type="publication", artefact_id=publication.id
        )
        proposal_events = (
            self.workflow_events.list(
                artefact_type="issue_proposal", artefact_id=proposal.id
            )
            if proposal
            else []
        )

        return PublicationInspection(
            publication=publication,
            proposal=proposal,
            optimisation_request=optimisation_request,
            sections=self._sections_for(publication),
            proposal_reviews=self.reviews.list(
                artefact_type="issue_proposal", artefact_id=publication.proposal_id
            ),
            publication_workflow_events=publication_events,
            proposal_workflow_events=proposal_events,
            rendered_outputs=self._rendered_outputs_from(publication_events),
            metadata=publication.metadata,
        )

    def _summary_for(self, publication: Publication) -> PublicationInspectionSummary:
        publication_events = self.workflow_events.list(
            artefact_type="publication", artefact_id=publication.id
        )
        return PublicationInspectionSummary(
            publication_id=publication.id,
            created_at=publication.created_at,
            title=publication.title,
            subtitle=publication.subtitle,
            proposal_id=publication.proposal_id,
            section_count=len(publication.sections),
            article_count=sum(
                len(section.article_ids) for section in publication.sections
            ),
            rendered_output_count=len(self._rendered_outputs_from(publication_events)),
            status=self._status_for(publication_events),
        )

    def _sections_for(
        self, publication: Publication
    ) -> list[PublicationSectionInspection]:
        return [
            PublicationSectionInspection(
                section=section,
                order=index + 1,
                articles=[
                    self._article_inspection_for(article_id)
                    for article_id in section.article_ids
                ],
            )
            for index, section in enumerate(publication.sections)
        ]

    def _article_inspection_for(self, article_id: UUID) -> PublicationArticleInspection:
        article = self.articles.get(article_id)
        return PublicationArticleInspection(
            article=article,
            article_id=article_id,
            reading_minutes=self._reading_minutes(article_id),
            relevance_score=self._relevance_score(article_id),
            relevance_rationale=self._relevance_rationale(article_id),
        )

    def _optimisation_request_for(
        self, proposal: IssueProposal | None
    ) -> OptimisationRequest | None:
        if proposal is None:
            return None
        raw_id = proposal.metadata.get("optimisation_request_id")
        if raw_id is None:
            return None
        try:
            return self.optimisation_requests.get(UUID(str(raw_id)))
        except ValueError:
            return None

    def _reading_minutes(self, article_id: UUID) -> int | float | None:
        for extraction in self.extractions.list(article_id=article_id):
            if extraction.kind == "reading_time":
                value = extraction.payload.get("reading_minutes")
                if isinstance(value, int | float):
                    return value
        return None

    def _relevance_score(self, article_id: UUID) -> float | None:
        relevance = self._relevance_evaluation(article_id)
        return relevance.score if relevance else None

    def _relevance_rationale(self, article_id: UUID) -> str | None:
        relevance = self._relevance_evaluation(article_id)
        return relevance.rationale if relevance else None

    def _relevance_evaluation(self, article_id: UUID) -> Evaluation | None:
        for evaluation in self.evaluations.list(article_id=article_id):
            if evaluation.kind == "relevance":
                return evaluation
        return None

    def _rendered_outputs_from(
        self, events: list[WorkflowEvent]
    ) -> list[RenderedOutputInspection]:
        outputs: list[RenderedOutputInspection] = []
        for event in events:
            if event.event_type != "publication-published":
                continue
            outputs.append(
                RenderedOutputInspection(
                    event_id=event.id,
                    format=event.payload.get("format"),
                    output_path=event.payload.get("output_path"),
                    created_at=event.created_at,
                )
            )
        return outputs

    def _status_for(self, events: list[WorkflowEvent]) -> str | None:
        if any(event.event_type == "publication-published" for event in events):
            return "rendered"
        if any(event.event_type == "publication-created" for event in events):
            return "created"
        return None
