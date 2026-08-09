from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from editorial.evaluators import EvaluatorDescriptor
from editorial.extractors import ExtractorDescriptor
from editorial.models import (
    IssueProposal,
    OptimisationRequest,
    Publication,
    Review,
    ReviewDecision,
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
from editorial.workflow import WorkflowProjection

WorkflowStageStatus = Literal[
    "complete",
    "incomplete",
    "pending",
    "changes_requested",
    "rejected",
    "not_configured",
]


class WorkflowProcessorCoverage(BaseModel):
    key: str
    display_name: str
    kind: str
    present: int
    missing: int


class WorkflowCoverage(BaseModel):
    configured_processors: int
    expected_operations: int
    present: int
    missing: int
    complete_articles: int
    articles_with_missing: int
    by_processor: list[WorkflowProcessorCoverage]


class WorkflowReviewSummary(BaseModel):
    review_id: UUID
    reviewer: str
    decision: str
    comments: str | None = None


class WorkflowPublicationSummary(BaseModel):
    publication_id: UUID
    title: str
    approved_review_id: UUID | None = None
    parent_publication_id: UUID | None = None
    rendered_output_count: int


class WorkflowStage(BaseModel):
    name: str
    status: WorkflowStageStatus
    summary: str
    command: str


class WorkflowOutstandingAction(BaseModel):
    action: str
    reason: str
    command: str


class WorkflowOverview(BaseModel):
    publication_name: str
    proposal: IssueProposal
    optimisation_request: OptimisationRequest | None = None
    proposal_event_state: str
    article_count: int
    missing_article_ids: list[UUID]
    extraction_coverage: WorkflowCoverage
    evaluation_coverage: WorkflowCoverage
    reviews: list[WorkflowReviewSummary]
    revision_requests: list[OptimisationRequest]
    publications: list[WorkflowPublicationSummary]
    stages: list[WorkflowStage]
    outstanding_actions: list[WorkflowOutstandingAction]
    overall_status: str


class WorkflowOverviewService:
    def __init__(
        self,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
        evaluations: SQLiteEvaluationRepository,
        proposals: SQLiteIssueProposalRepository,
        optimisation_requests: SQLiteOptimisationRequestRepository,
        reviews: SQLiteReviewRepository,
        publications: SQLitePublicationRepository,
        workflow_events: SQLiteWorkflowEventRepository,
    ):
        self.articles = articles
        self.extractions = extractions
        self.evaluations = evaluations
        self.proposals = proposals
        self.optimisation_requests = optimisation_requests
        self.reviews = reviews
        self.publications = publications
        self.workflow_events = workflow_events

    def build(
        self,
        proposal_id: UUID,
        publication_name: str,
        extractor_descriptors: list[ExtractorDescriptor],
        evaluator_descriptors: list[EvaluatorDescriptor],
        *,
        config_path: Path,
        db_path: Path,
    ) -> WorkflowOverview:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ValueError(f"Issue proposal not found: {proposal_id}")
        self._validate_descriptors(extractor_descriptors, "extractor")
        self._validate_descriptors(evaluator_descriptors, "evaluator")

        article_ids = set(proposal.article_ids)
        stored_article_ids = {
            article.id for article in self.articles.list() if article.id in article_ids
        }
        missing_article_ids = sorted(article_ids - stored_article_ids)
        extraction_coverage = self._coverage(
            article_ids,
            extractor_descriptors,
            [
                (item.article_id, item.extractor, item.kind)
                for item in self.extractions.list()
                if item.article_id in article_ids
            ],
        )
        evaluation_coverage = self._coverage(
            article_ids,
            evaluator_descriptors,
            [
                (item.article_id, item.evaluator, item.kind)
                for item in self.evaluations.list()
                if item.article_id in article_ids
            ],
        )
        optimisation_request = self._optimisation_request_for(proposal)
        reviews = self.reviews.list(
            artefact_type="issue_proposal", artefact_id=proposal.id
        )
        publications = [
            publication
            for publication in self.publications.list()
            if publication.proposal_id == proposal.id
        ]
        revision_requests = self._revision_requests_for(reviews)
        rendered_counts = {
            publication.id: self._rendered_output_count(publication)
            for publication in publications
        }
        proposal_events = self.workflow_events.list(
            artefact_type="issue_proposal", artefact_id=proposal.id
        )
        context = _WorkflowContext(
            proposal=proposal,
            optimisation_request=optimisation_request,
            reviews=reviews,
            revision_requests=revision_requests,
            publications=publications,
            rendered_counts=rendered_counts,
            missing_article_ids=missing_article_ids,
            extraction_coverage=extraction_coverage,
            evaluation_coverage=evaluation_coverage,
            config_path=config_path,
            db_path=db_path,
        )
        stages = self._stages(context)
        actions = self._outstanding_actions(context)
        return WorkflowOverview(
            publication_name=publication_name,
            proposal=proposal,
            optimisation_request=optimisation_request,
            proposal_event_state=WorkflowProjection().state_for(proposal_events),
            article_count=len(article_ids),
            missing_article_ids=missing_article_ids,
            extraction_coverage=extraction_coverage,
            evaluation_coverage=evaluation_coverage,
            reviews=[
                WorkflowReviewSummary(
                    review_id=review.id,
                    reviewer=review.reviewer,
                    decision=review.decision.value,
                    comments=review.comments,
                )
                for review in reviews
            ],
            revision_requests=revision_requests,
            publications=[
                WorkflowPublicationSummary(
                    publication_id=publication.id,
                    title=publication.title,
                    approved_review_id=publication.approved_review_id,
                    parent_publication_id=publication.parent_publication_id,
                    rendered_output_count=rendered_counts[publication.id],
                )
                for publication in publications
            ],
            stages=stages,
            outstanding_actions=actions,
            overall_status=self._overall_status(context),
        )

    def _coverage(
        self,
        article_ids: set[UUID],
        descriptors: list[ExtractorDescriptor] | list[EvaluatorDescriptor],
        stored_operations: list[tuple[UUID, str, str]],
    ) -> WorkflowCoverage:
        stored = set(stored_operations)
        expected = {
            (article_id, descriptor.key, descriptor.kind)
            for article_id in article_ids
            for descriptor in descriptors
        }
        complete_articles = sum(
            all(
                (article_id, descriptor.key, descriptor.kind) in stored
                for descriptor in descriptors
            )
            for article_id in article_ids
        )
        by_processor = []
        for descriptor in descriptors:
            present = sum(
                (article_id, descriptor.key, descriptor.kind) in stored
                for article_id in article_ids
            )
            by_processor.append(
                WorkflowProcessorCoverage(
                    key=descriptor.key,
                    display_name=descriptor.display_name,
                    kind=descriptor.kind,
                    present=present,
                    missing=len(article_ids) - present,
                )
            )
        present = len(expected & stored)
        return WorkflowCoverage(
            configured_processors=len(descriptors),
            expected_operations=len(expected),
            present=present,
            missing=len(expected) - present,
            complete_articles=complete_articles if descriptors else 0,
            articles_with_missing=(
                len(article_ids) - complete_articles
                if descriptors
                else len(article_ids)
            ),
            by_processor=by_processor,
        )

    def _stages(self, context: _WorkflowContext) -> list[WorkflowStage]:
        config = str(context.config_path)
        db = str(context.db_path)
        proposal_id = context.proposal.id
        latest_review = context.latest_review
        composed_publication = context.composed_publication
        return [
            WorkflowStage(
                name="Articles",
                status="complete" if not context.missing_article_ids else "incomplete",
                summary=(
                    f"{len(context.proposal.article_ids)} selected Article records are available."
                    if not context.missing_article_ids
                    else f"{len(context.missing_article_ids)} selected Article records are missing."
                ),
                command=f"editorial proposal show {proposal_id} --db {db}",
            ),
            self._coverage_stage(
                "Extraction",
                context.extraction_coverage,
                f"editorial extraction coverage --config {config} --db {db}",
            ),
            self._coverage_stage(
                "Evaluation",
                context.evaluation_coverage,
                f"editorial evaluation list --db {db}",
            ),
            WorkflowStage(
                name="Proposal",
                status="complete",
                summary=(
                    f"IssueProposal selects {len(context.proposal.article_ids)} articles "
                    f"with objective value {context.proposal.objective_value}."
                ),
                command=f"editorial explain proposal {proposal_id} --db {db}",
            ),
            WorkflowStage(
                name="Review",
                status=self._review_status(latest_review),
                summary=self._review_summary(latest_review),
                command=(
                    f"editorial review show {latest_review.id} --db {db}"
                    if latest_review
                    else f"editorial proposal show {proposal_id} --db {db}"
                ),
            ),
            WorkflowStage(
                name="Composition",
                status="complete" if composed_publication else "pending",
                summary=self._composition_summary(latest_review, composed_publication),
                command=(
                    f"editorial publication show {composed_publication.id} --db {db}"
                    if composed_publication
                    else f"editorial publication list --db {db}"
                ),
            ),
            WorkflowStage(
                name="Rendering",
                status=(
                    "complete"
                    if composed_publication
                    and context.rendered_counts[composed_publication.id]
                    else "pending"
                ),
                summary=self._rendering_summary(context, composed_publication),
                command=(
                    f"editorial publication show {composed_publication.id} --db {db}"
                    if composed_publication
                    else f"editorial publication list --db {db}"
                ),
            ),
        ]

    def _outstanding_actions(
        self, context: _WorkflowContext
    ) -> list[WorkflowOutstandingAction]:
        actions: list[WorkflowOutstandingAction] = []
        config = str(context.config_path)
        db = str(context.db_path)
        proposal_id = context.proposal.id
        article_options = " ".join(
            f"--article-id {article_id}" for article_id in context.proposal.article_ids
        )
        if context.missing_article_ids:
            actions.append(
                WorkflowOutstandingAction(
                    action="Investigate missing Articles",
                    reason="The proposal references Article records that are not available.",
                    command=f"editorial proposal show {proposal_id} --db {db}",
                )
            )
        if not context.missing_article_ids and context.extraction_coverage.missing:
            actions.append(
                WorkflowOutstandingAction(
                    action="Complete extraction coverage",
                    reason=(
                        f"{context.extraction_coverage.missing} configured extraction "
                        "operations are missing for selected articles."
                    ),
                    command=(
                        f"editorial extract --config {config} --db {db} "
                        f"{article_options} --missing-only"
                    ),
                )
            )
        if not context.missing_article_ids and context.evaluation_coverage.missing:
            actions.append(
                WorkflowOutstandingAction(
                    action="Complete evaluation coverage",
                    reason=(
                        f"{context.evaluation_coverage.missing} configured evaluation "
                        "operations are missing for selected articles."
                    ),
                    command=(
                        f"editorial evaluate --config {config} --db {db} "
                        f"{article_options} --missing-only"
                    ),
                )
            )

        latest_review = context.latest_review
        if latest_review is None:
            actions.append(
                WorkflowOutstandingAction(
                    action="Review the proposal",
                    reason="No editorial Review has been recorded for this proposal.",
                    command=f"editorial proposal show {proposal_id} --db {db}",
                )
            )
            return actions
        if latest_review.decision == ReviewDecision.NEEDS_CHANGES:
            actions.extend(self._revision_actions(context, latest_review))
            return actions
        if latest_review.decision == ReviewDecision.REJECT:
            actions.append(
                WorkflowOutstandingAction(
                    action="Decide whether to create a new optimisation request",
                    reason="The latest Review rejects this proposal.",
                    command=f"editorial review show {latest_review.id} --db {db}",
                )
            )
            return actions
        if latest_review.decision == ReviewDecision.COMMENT:
            actions.append(
                WorkflowOutstandingAction(
                    action="Record a decisive review",
                    reason="The latest Review comments without approving or rejecting.",
                    command=f"editorial review show {latest_review.id} --db {db}",
                )
            )
            return actions

        publication = context.composed_publication
        if publication is None:
            actions.append(
                WorkflowOutstandingAction(
                    action="Compose the approved publication",
                    reason="The latest approval has no linked Publication.",
                    command=(
                        "editorial publication compose "
                        f"--proposal-id {proposal_id} "
                        f"--approved-review-id {latest_review.id} "
                        f"--composition COMPOSITION.yaml --db {db}"
                    ),
                )
            )
        elif not context.rendered_counts[publication.id]:
            actions.append(
                WorkflowOutstandingAction(
                    action="Render the publication",
                    reason="The composed Publication has no recorded rendered output.",
                    command=(
                        "editorial publish markdown "
                        f"--publication-id {publication.id} "
                        f"--output PUBLICATION.md --db {db}"
                    ),
                )
            )
        return actions

    def _revision_actions(
        self, context: _WorkflowContext, review: Review
    ) -> list[WorkflowOutstandingAction]:
        db = str(context.db_path)
        config = str(context.config_path)
        requests = [
            request
            for request in context.revision_requests
            if request.metadata.get("source_review_id") == str(review.id)
        ]
        if not requests:
            return [
                WorkflowOutstandingAction(
                    action="Create a revision request",
                    reason="The latest Review requests changes but has no revision request.",
                    command=(
                        f"editorial review revise {review.id} --config {config} --db {db}"
                    ),
                )
            ]
        request = requests[0]
        child_proposals = [
            proposal
            for proposal in self.proposals.list()
            if proposal.metadata.get("optimisation_request_id") == str(request.id)
        ]
        if not child_proposals:
            return [
                WorkflowOutstandingAction(
                    action="Run the revision request",
                    reason="A revision request exists but has not produced a proposal.",
                    command=f"editorial optimisation-request run {request.id} --db {db}",
                )
            ]
        candidate = child_proposals[0]
        return [
            WorkflowOutstandingAction(
                action="Compare the revised proposal",
                reason="A candidate proposal exists for the requested changes.",
                command=(
                    f"editorial proposal compare {context.proposal.id} "
                    f"{candidate.id} --db {db}"
                ),
            )
        ]

    def _overall_status(self, context: _WorkflowContext) -> str:
        publication = context.composed_publication
        evidence_gaps = bool(
            context.missing_article_ids
            or context.extraction_coverage.missing
            or context.evaluation_coverage.missing
        )
        if publication and context.rendered_counts[publication.id]:
            return "rendered_with_evidence_gaps" if evidence_gaps else "rendered"
        if publication:
            return "composed"
        review = context.latest_review
        if review is None:
            return "awaiting_review"
        if review.decision == ReviewDecision.APPROVE:
            return "approved"
        if review.decision == ReviewDecision.NEEDS_CHANGES:
            return "changes_requested"
        if review.decision == ReviewDecision.REJECT:
            return "rejected"
        return "awaiting_decision"

    def _optimisation_request_for(
        self, proposal: IssueProposal
    ) -> OptimisationRequest | None:
        raw_id = proposal.metadata.get("optimisation_request_id")
        if raw_id is None:
            return None
        try:
            return self.optimisation_requests.get(UUID(str(raw_id)))
        except ValueError:
            return None

    def _revision_requests_for(
        self, reviews: list[Review]
    ) -> list[OptimisationRequest]:
        review_ids = {str(review.id) for review in reviews}
        return [
            request
            for request in self.optimisation_requests.list()
            if request.metadata.get("source_review_id") in review_ids
        ]

    def _rendered_output_count(self, publication: Publication) -> int:
        return sum(
            event.event_type == "publication-published"
            for event in self.workflow_events.list(
                artefact_type="publication", artefact_id=publication.id
            )
        )

    @staticmethod
    def _coverage_stage(
        name: str, coverage: WorkflowCoverage, command: str
    ) -> WorkflowStage:
        if not coverage.configured_processors:
            status: WorkflowStageStatus = "not_configured"
            summary = f"No enabled {name.lower()} processors are configured."
        elif coverage.missing:
            status = "incomplete"
            summary = (
                f"{coverage.present} of {coverage.expected_operations} configured "
                f"{name.lower()} operations are present; {coverage.missing} are missing."
            )
        else:
            status = "complete"
            summary = (
                f"All {coverage.expected_operations} configured "
                f"{name.lower()} operations are present."
            )
        return WorkflowStage(
            name=name,
            status=status,
            summary=summary,
            command=command,
        )

    @staticmethod
    def _review_status(review: Review | None) -> WorkflowStageStatus:
        if review is None or review.decision == ReviewDecision.COMMENT:
            return "pending"
        if review.decision == ReviewDecision.APPROVE:
            return "complete"
        if review.decision == ReviewDecision.NEEDS_CHANGES:
            return "changes_requested"
        return "rejected"

    @staticmethod
    def _review_summary(review: Review | None) -> str:
        if review is None:
            return "No Review has been recorded for this proposal."
        return (
            f"Latest Review {review.id} by {review.reviewer} records "
            f"{review.decision.value}."
        )

    @staticmethod
    def _rendering_summary(
        context: _WorkflowContext, publication: Publication | None
    ) -> str:
        if publication is None:
            return "No approved Publication is available to render."
        count = context.rendered_counts[publication.id]
        if count:
            return f"Publication {publication.id} has {count} rendered output(s)."
        return f"Publication {publication.id} has no rendered output."

    @staticmethod
    def _composition_summary(
        review: Review | None, publication: Publication | None
    ) -> str:
        if publication:
            return f"Publication {publication.id} records the approved composition."
        if review is None or review.decision != ReviewDecision.APPROVE:
            return "The proposal does not have a current approval to compose."
        return "No Publication is linked to the latest approval."

    @staticmethod
    def _validate_descriptors(
        descriptors: list[ExtractorDescriptor] | list[EvaluatorDescriptor], label: str
    ) -> None:
        keys = [descriptor.key for descriptor in descriptors]
        duplicate_keys = {key for key in keys if keys.count(key) > 1}
        if duplicate_keys:
            raise ValueError(
                f"Duplicate configured {label} keys cannot be summarised: "
                + ", ".join(sorted(duplicate_keys))
            )


class _WorkflowContext(BaseModel):
    proposal: IssueProposal
    optimisation_request: OptimisationRequest | None
    reviews: list[Review]
    revision_requests: list[OptimisationRequest]
    publications: list[Publication]
    rendered_counts: dict[UUID, int]
    missing_article_ids: list[UUID]
    extraction_coverage: WorkflowCoverage
    evaluation_coverage: WorkflowCoverage
    config_path: Path
    db_path: Path

    @property
    def latest_review(self) -> Review | None:
        return self.reviews[-1] if self.reviews else None

    @property
    def composed_publication(self) -> Publication | None:
        review = self.latest_review
        if review is None or review.decision != ReviewDecision.APPROVE:
            return None
        return next(
            (
                publication
                for publication in self.publications
                if publication.approved_review_id == review.id
            ),
            None,
        )
