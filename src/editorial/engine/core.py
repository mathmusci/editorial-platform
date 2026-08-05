from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, Literal
from uuid import UUID
from editorial.interfaces import Evaluator, Extractor, Optimiser, Provider
from editorial.models import Article, OptimisationRequest, WorkflowEvent
from editorial.storage import (
    ArticleInsertOutcome,
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
    skipped: int = 0
    failed: int = 0

    @property
    def operations(self) -> int:
        return self.articles * self.evaluators


@dataclass(frozen=True)
class EvaluationProgress:
    completed: int
    total: int
    stored: int
    skipped: int
    failed: int
    article_id: UUID
    article_title: str
    evaluator_name: str
    provider: str | None
    model: str | None
    outcome: Literal["started", "stored", "skipped", "failed"]


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

                outcome = self.article_repository.insert(article)
                if outcome is ArticleInsertOutcome.ALREADY_EXISTS:
                    already_in_database += 1
                else:
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
        limit: int | None = None,
        offset: int = 0,
        article_ids: Iterable[UUID] | None = None,
        missing_only: bool = False,
        force: bool = False,
    ) -> ExtractionRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run extractors")
        if limit is not None and limit <= 0:
            raise ValueError("Extraction limit must be a positive integer")
        if offset < 0:
            raise ValueError("Extraction offset must be zero or greater")
        if missing_only and force:
            raise ValueError("Extraction cannot use missing_only and force together")

        extractor_list = list(extractors)
        _validate_unique_processor_keys(
            [
                _extractor_progress_metadata(extractor).extractor_key
                for extractor in extractor_list
            ],
            "extractor",
        )
        articles = _select_articles(
            self.article_repository.list(), article_ids=article_ids
        )
        if offset:
            articles = articles[offset:]
        if limit is not None:
            articles = articles[:limit]
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
                if missing_only and self.extraction_repository.exists_for_operation(
                    article.id, metadata.extractor_key
                ):
                    completed += 1
                    skipped += 1
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
                                outcome="skipped",
                            )
                        )
                    continue
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

    def evaluate(
        self,
        evaluators: Iterable[Evaluator],
        progress: Callable[[EvaluationProgress], None] | None = None,
        limit: int | None = None,
        offset: int = 0,
        article_ids: Iterable[UUID] | None = None,
        missing_only: bool = False,
        force: bool = False,
    ) -> EvaluationRunResult:
        if self.extraction_repository is None:
            raise ValueError("Extraction repository is required to run evaluators")
        if self.evaluation_repository is None:
            raise ValueError("Evaluation repository is required to run evaluators")
        if limit is not None and limit <= 0:
            raise ValueError("Evaluation limit must be a positive integer")
        if offset < 0:
            raise ValueError("Evaluation offset must be zero or greater")
        if missing_only and force:
            raise ValueError("Evaluation cannot use missing_only and force together")

        evaluator_list = list(evaluators)
        _validate_unique_processor_keys(
            [
                _evaluator_progress_metadata(evaluator).evaluator_key
                for evaluator in evaluator_list
            ],
            "evaluator",
        )
        articles = _select_articles(
            self.article_repository.list(),
            article_ids=article_ids,
            operation="evaluation",
        )
        if offset:
            articles = articles[offset:]
        if limit is not None:
            articles = articles[:limit]
        total = len(articles) * len(evaluator_list)
        completed = stored = skipped = failed = 0
        for article in articles:
            extractions = self.extraction_repository.list(article_id=article.id)
            for evaluator in evaluator_list:
                metadata = _evaluator_progress_metadata(evaluator)
                if progress is not None:
                    progress(
                        EvaluationProgress(
                            completed=completed,
                            total=total,
                            stored=stored,
                            skipped=skipped,
                            failed=failed,
                            article_id=article.id,
                            article_title=article.title,
                            evaluator_name=metadata.evaluator_name,
                            provider=metadata.provider,
                            model=metadata.model,
                            outcome="started",
                        )
                    )
                if missing_only and self.evaluation_repository.exists_for_operation(
                    article.id, metadata.evaluator_key
                ):
                    completed += 1
                    skipped += 1
                    if progress is not None:
                        progress(
                            EvaluationProgress(
                                completed=completed,
                                total=total,
                                stored=stored,
                                skipped=skipped,
                                failed=failed,
                                article_id=article.id,
                                article_title=article.title,
                                evaluator_name=metadata.evaluator_name,
                                provider=metadata.provider,
                                model=metadata.model,
                                outcome="skipped",
                            )
                        )
                    continue
                try:
                    evaluation = evaluator.evaluate(article, extractions)
                    self.evaluation_repository.insert(evaluation)
                except Exception:
                    completed += 1
                    failed += 1
                    if progress is not None:
                        progress(
                            EvaluationProgress(
                                completed=completed,
                                total=total,
                                stored=stored,
                                skipped=skipped,
                                failed=failed,
                                article_id=article.id,
                                article_title=article.title,
                                evaluator_name=metadata.evaluator_name,
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
                        EvaluationProgress(
                            completed=completed,
                            total=total,
                            stored=stored,
                            skipped=skipped,
                            failed=failed,
                            article_id=article.id,
                            article_title=article.title,
                            evaluator_name=metadata.evaluator_name,
                            provider=metadata.provider,
                            model=metadata.model,
                            outcome="stored",
                        )
                    )
        return EvaluationRunResult(
            articles=len(articles),
            evaluators=len(evaluator_list),
            stored=stored,
            skipped=skipped,
            failed=failed,
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
    extractor_key: str
    extractor_name: str
    provider: str | None
    model: str | None


def _extractor_progress_metadata(extractor: Extractor) -> _ExtractorProgressMetadata:
    provider = getattr(extractor, "provider", None)
    provider_name = getattr(provider, "name", None)
    model = getattr(provider, "model", None)
    extractor_key = str(getattr(extractor, "name", "unknown"))
    return _ExtractorProgressMetadata(
        extractor_key=extractor_key,
        extractor_name=str(getattr(extractor, "display_name", extractor_key)),
        provider=str(provider_name) if provider_name is not None else None,
        model=str(model) if model is not None else None,
    )


@dataclass(frozen=True)
class _EvaluatorProgressMetadata:
    evaluator_key: str
    evaluator_name: str
    provider: str | None
    model: str | None


def _evaluator_progress_metadata(evaluator: Evaluator) -> _EvaluatorProgressMetadata:
    provider = getattr(evaluator, "provider", None)
    provider_name = getattr(provider, "name", None)
    model = getattr(provider, "model", None)
    evaluator_key = str(getattr(evaluator, "name", "unknown"))
    return _EvaluatorProgressMetadata(
        evaluator_key=evaluator_key,
        evaluator_name=str(getattr(evaluator, "display_name", evaluator_key)),
        provider=str(provider_name) if provider_name is not None else None,
        model=str(model) if model is not None else None,
    )


def _validate_unique_processor_keys(keys: list[str], processor: str) -> None:
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        duplicate_text = ", ".join(repr(key) for key in duplicates)
        raise ValueError(
            f"Configured {processor} keys must be unique; duplicate keys: "
            f"{duplicate_text}. Set an explicit key for each configured {processor}."
        )


def _select_articles(
    articles: list[Article],
    article_ids: Iterable[UUID] | None,
    operation: str = "extraction",
) -> list[Article]:
    if article_ids is None:
        return articles
    requested = set(article_ids)
    selected = [article for article in articles if article.id in requested]
    missing = requested - {article.id for article in selected}
    if missing:
        missing_text = ", ".join(str(article_id) for article_id in sorted(missing))
        raise ValueError(f"Article not found for {operation}: {missing_text}")
    return selected
