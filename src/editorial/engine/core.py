from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, Literal
from uuid import UUID
from editorial.interfaces import Evaluator, Extractor, Optimiser, Provider
from editorial.models import Article, OptimisationRequest, WorkflowEvent
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLiteWorkflowEventRepository,
)


@dataclass(frozen=True)
class IngestResult:
    fetched: int
    added: int
    duplicates_in_source: int
    already_in_database: int

    @property
    def inserted(self) -> int:
        return self.added

    @property
    def skipped_duplicates(self) -> int:
        return self.duplicates_in_source + self.already_in_database


@dataclass(frozen=True)
class ExtractionRunResult:
    articles: int
    extractors: int
    stored: int
    skipped: int = 0
    failed: int = 0

    @property
    def operations(self) -> int:
        return self.articles * self.extractors


@dataclass(frozen=True)
class ExtractionProgress:
    completed: int
    total: int
    stored: int
    skipped: int
    failed: int
    article_id: UUID
    article_title: str
    extractor_name: str
    provider: str | None
    model: str | None
    outcome: Literal["started", "stored", "skipped", "failed"]


@dataclass(frozen=True)
class EvaluationRunResult:
    articles: int
    evaluators: int
    stored: int


@dataclass(frozen=True)
class OptimisationRunResult:
    proposal_id: str
    optimiser: str
    selected_articles: int
    objective_value: float
    constraint_results: int
    request_id: str | None = None


class EditorialEngine:
    def __init__(
        self,
        article_repository: SQLiteArticleRepository,
        extraction_repository: SQLiteExtractionRepository | None = None,
        evaluation_repository: SQLiteEvaluationRepository | None = None,
        issue_proposal_repository: SQLiteIssueProposalRepository | None = None,
        workflow_event_repository: SQLiteWorkflowEventRepository | None = None,
    ):
        self.article_repository = article_repository
        self.extraction_repository = extraction_repository
        self.evaluation_repository = evaluation_repository
        self.issue_proposal_repository = issue_proposal_repository
        self.workflow_event_repository = workflow_event_repository

    def ingest(self, providers: Iterable[Provider]) -> IngestResult:
        fetched = added = duplicates_in_source = already_in_database = 0
        seen_identities: set[str] = set()
        for provider in providers:
            for article in provider.fetch():
                fetched += 1
                identity = self._article_identity(article)
                if identity in seen_identities:
                    duplicates_in_source += 1
                    continue
                seen_identities.add(identity)

                if self.article_repository.exists(article):
                    already_in_database += 1
                else:
                    self.article_repository.upsert(article)
                    added += 1
        return IngestResult(
            fetched=fetched,
            added=added,
            duplicates_in_source=duplicates_in_source,
            already_in_database=already_in_database,
        )

    def _article_identity(self, article: Article) -> str:
        return str(article.url) if article.url is not None else str(article.id)

    def extract(
        self,
        extractors: Iterable[Extractor],
        progress: Callable[[ExtractionProgress], None] | None = None,
    ) -> ExtractionRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run extractors")

        extractor_list = list(extractors)
        articles = self.article_repository.list()
        total = len(articles) * len(extractor_list)
        completed = stored = skipped = failed = 0
        for article in articles:
            for extractor in extractor_list:
                metadata = _extractor_progress_metadata(extractor)
                if progress is not None:
                    progress(
                        ExtractionProgress(
                            completed=completed,
                            total=total,
                            stored=stored,
                            skipped=skipped,
                            failed=failed,
                            article_id=article.id,
                            article_title=article.title,
                            extractor_name=metadata.extractor_name,
                            provider=metadata.provider,
                            model=metadata.model,
                            outcome="started",
                        )
                    )
                try:
                    extraction = extractor.extract(article)
                    self.extraction_repository.insert(extraction)
                except Exception:
                    completed += 1
                    failed += 1
                    if progress is not None:
                        progress(
                            ExtractionProgress(
                                completed=completed,
                                total=total,
                                stored=stored,
                                skipped=skipped,
                                failed=failed,
                                article_id=article.id,
                                article_title=article.title,
                                extractor_name=metadata.extractor_name,
                                provider=metadata.provider,
                                model=metadata.model,
                                outcome="failed",
                            )
                        )
                    raise
                completed += 1
                stored += 1
                if progress is not None:
                    progress(
                        ExtractionProgress(
                            completed=completed,
                            total=total,
                            stored=stored,
                            skipped=skipped,
                            failed=failed,
                            article_id=article.id,
                            article_title=article.title,
                            extractor_name=metadata.extractor_name,
                            provider=metadata.provider,
                            model=metadata.model,
                            outcome="stored",
                        )
                    )
        return ExtractionRunResult(
            articles=len(articles),
            extractors=len(extractor_list),
            stored=stored,
            skipped=skipped,
            failed=failed,
        )

    def evaluate(self, evaluators: Iterable[Evaluator]) -> EvaluationRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run evaluators")
        if self.evaluation_repository is None:
            raise ValueError("Evaluation repository is required to run evaluators")

        evaluator_list = list(evaluators)
        articles = self.article_repository.list()
        stored = 0
        for article in articles:
            extractions = self.extraction_repository.list(article_id=article.id)
            for evaluator in evaluator_list:
                evaluation = evaluator.evaluate(article, extractions)
                self.evaluation_repository.insert(evaluation)
                stored += 1
        return EvaluationRunResult(
            articles=len(articles), evaluators=len(evaluator_list), stored=stored
        )

    def optimise(self, optimiser: Optimiser) -> OptimisationRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run optimiser")
        if self.evaluation_repository is None:
            raise ValueError("Evaluation repository is required to run optimiser")
        if self.issue_proposal_repository is None:
            raise ValueError("Issue proposal repository is required to run optimiser")

        proposal = optimiser.optimise(
            articles=self.article_repository.list(),
            extractions=self.extraction_repository.list(),
            evaluations=self.evaluation_repository.list(),
        )
        self.issue_proposal_repository.insert(proposal)
        return OptimisationRunResult(
            proposal_id=str(proposal.id),
            optimiser=proposal.optimiser,
            selected_articles=len(proposal.article_ids),
            objective_value=proposal.objective_value,
            constraint_results=len(proposal.constraint_results),
        )

    def optimise_request(
        self, optimiser: Optimiser, request: OptimisationRequest
    ) -> OptimisationRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run optimiser")
        if self.evaluation_repository is None:
            raise ValueError("Evaluation repository is required to run optimiser")
        if self.issue_proposal_repository is None:
            raise ValueError("Issue proposal repository is required to run optimiser")

        proposal = optimiser.execute(
            request=request,
            articles=self.article_repository.list(),
            extractions=self.extraction_repository.list(),
            evaluations=self.evaluation_repository.list(),
        )
        self.issue_proposal_repository.insert(proposal)
        if self.workflow_event_repository is not None:
            self.workflow_event_repository.insert(
                WorkflowEvent(
                    artefact_type="issue_proposal",
                    artefact_id=proposal.id,
                    event_type="proposal-created",
                    actor=request.created_by,
                    reason="Created from optimisation request",
                    payload={
                        "optimisation_request_id": str(request.id),
                        "strategy": request.strategy,
                    },
                )
            )
        return OptimisationRunResult(
            proposal_id=str(proposal.id),
            optimiser=proposal.optimiser,
            selected_articles=len(proposal.article_ids),
            objective_value=proposal.objective_value,
            constraint_results=len(proposal.constraint_results),
            request_id=str(request.id),
        )


@dataclass(frozen=True)
class _ExtractorProgressMetadata:
    extractor_name: str
    provider: str | None
    model: str | None


def _extractor_progress_metadata(extractor: Extractor) -> _ExtractorProgressMetadata:
    provider = getattr(extractor, "provider", None)
    provider_name = getattr(provider, "name", None)
    model = getattr(provider, "model", None)
    return _ExtractorProgressMetadata(
        extractor_name=str(
            getattr(extractor, "display_name", getattr(extractor, "name", "unknown"))
        ),
        provider=str(provider_name) if provider_name is not None else None,
        model=str(model) if model is not None else None,
    )
