from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

from editorial.config import load_publication_config
from editorial.engine import (
    EditorialEngine,
    EvaluationProgress,
    EvaluationRunResult,
    ExtractionProgress,
    ExtractionRunResult,
    IngestResult,
)
from editorial.evaluators import build_evaluator
from editorial.extractors import build_extractor
from editorial.models import (
    ProcessingKind,
    ProcessingRun,
    ProcessingRunOptions,
    WorkflowEvent,
    utc_now,
)
from editorial.providers import build_provider
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
    SQLiteProcessingRunRepository,
    SQLiteWorkflowEventRepository,
)

ProcessingProgress: TypeAlias = ExtractionProgress | EvaluationProgress
ProcessingResult: TypeAlias = IngestResult | ExtractionRunResult | EvaluationRunResult


class ProcessingRunService:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).resolve()
        self.runs = SQLiteProcessingRunRepository(self.database_path)
        self.events = SQLiteWorkflowEventRepository(self.database_path)

    def create_run(
        self,
        kind: ProcessingKind,
        config_path: str | Path,
        options: ProcessingRunOptions | None = None,
    ) -> ProcessingRun:
        config_path = Path(config_path).resolve()
        config = load_publication_config(config_path)
        run = ProcessingRun(
            kind=kind,
            publication_name=config.publication.name,
            config_path=str(config_path),
            database_path=str(self.database_path),
            config_digest=_config_digest(config_path),
            options=options or ProcessingRunOptions(),
        )
        self.runs.insert(run)
        self._record_event(run, "processing-run-queued")
        return run

    def execute(
        self,
        run_id: UUID,
        progress: Callable[[ProcessingProgress], None] | None = None,
        *,
        raise_on_failure: bool = True,
    ) -> ProcessingResult | None:
        run = self._required_run(run_id)
        started_at = utc_now()
        run = run.model_copy(
            update={
                "status": "running",
                "started_at": started_at,
                "updated_at": started_at,
            }
        )
        self.runs.update(run)
        self._record_event(run, "processing-run-started")
        try:
            config_path = Path(run.config_path)
            if _config_digest(config_path) != run.config_digest:
                raise RuntimeError(
                    "Configuration changed after this processing run was queued"
                )
            config = load_publication_config(config_path)
            result = self._execute_kind(run, config, progress)
            self._complete(run.id, result)
            return result
        except Exception as exc:
            self._fail(run.id, exc)
            if raise_on_failure:
                raise
            return None

    def interrupt_active_runs(self) -> list[ProcessingRun]:
        interrupted = []
        for run in self.runs.active():
            now = utc_now()
            updated = run.model_copy(
                update={
                    "status": "interrupted",
                    "error_message": "The process ended before this run completed",
                    "finished_at": now,
                    "updated_at": now,
                }
            )
            self.runs.update(updated)
            self._record_event(updated, "processing-run-interrupted")
            interrupted.append(updated)
        return interrupted

    def _execute_kind(
        self,
        run: ProcessingRun,
        config,
        progress: Callable[[ProcessingProgress], None] | None,
    ) -> ProcessingResult:
        if run.kind == "ingest":
            providers = [
                build_provider(item, base_path=config.base_path)
                for item in config.providers
                if item.enabled
            ]
            result = EditorialEngine(
                SQLiteArticleRepository(self.database_path)
            ).ingest(providers)
            self._record_ingest_result(run.id, len(providers), result)
            return result

        options = run.options
        if run.kind == "extract":
            processors = [
                build_extractor(item) for item in config.extractors if item.enabled
            ]
            engine = EditorialEngine(
                SQLiteArticleRepository(self.database_path),
                SQLiteExtractionRepository(self.database_path),
            )
            return engine.extract(
                processors,
                progress=self._progress_callback(run.id, len(processors), progress),
                limit=options.limit,
                offset=options.offset,
                article_ids=options.article_ids or None,
                missing_only=options.missing_only,
                force=options.force,
            )

        processors = [
            build_evaluator(item) for item in config.evaluators if item.enabled
        ]
        engine = EditorialEngine(
            SQLiteArticleRepository(self.database_path),
            SQLiteExtractionRepository(self.database_path),
            SQLiteEvaluationRepository(self.database_path),
        )
        return engine.evaluate(
            processors,
            progress=self._progress_callback(run.id, len(processors), progress),
            limit=options.limit,
            offset=options.offset,
            article_ids=options.article_ids or None,
            missing_only=options.missing_only,
            force=options.force,
        )

    def _progress_callback(
        self,
        run_id: UUID,
        processor_count: int,
        external: Callable[[ProcessingProgress], None] | None,
    ) -> Callable[[ProcessingProgress], None]:
        def observe(event: ProcessingProgress) -> None:
            run = self._required_run(run_id)
            processor = (
                event.extractor_name
                if isinstance(event, ExtractionProgress)
                else event.evaluator_name
            )
            run = run.model_copy(
                update={
                    "total_operations": event.total,
                    "article_count": (
                        event.total // processor_count if processor_count else 0
                    ),
                    "processor_count": processor_count,
                    "completed_operations": event.completed,
                    "stored_operations": event.stored,
                    "skipped_operations": event.skipped,
                    "failed_operations": event.failed,
                    "current_article_id": event.article_id,
                    "current_article_title": event.article_title,
                    "current_processor": processor,
                    "current_provider": event.provider,
                    "current_model": event.model,
                    "updated_at": utc_now(),
                }
            )
            self.runs.update(run)
            if external is not None:
                external(event)

        return observe

    def _record_ingest_result(
        self, run_id: UUID, provider_count: int, result: IngestResult
    ) -> None:
        run = self._required_run(run_id)
        updated = run.model_copy(
            update={
                "article_count": result.fetched,
                "processor_count": provider_count,
                "total_operations": result.fetched,
                "completed_operations": result.fetched,
                "stored_operations": result.added,
                "skipped_operations": result.skipped_duplicates,
                "result": {
                    "fetched": result.fetched,
                    "added": result.added,
                    "duplicates_in_source": result.duplicates_in_source,
                    "already_in_database": result.already_in_database,
                },
                "updated_at": utc_now(),
            }
        )
        self.runs.update(updated)

    def _complete(self, run_id: UUID, result: ProcessingResult) -> None:
        run = self._required_run(run_id)
        now = utc_now()
        updates = {
            "status": "completed",
            "finished_at": now,
            "updated_at": now,
        }
        if isinstance(result, ExtractionRunResult):
            updates.update(
                article_count=result.articles,
                processor_count=result.extractors,
                total_operations=result.operations,
                completed_operations=result.operations,
                stored_operations=result.stored,
                skipped_operations=result.skipped,
                failed_operations=result.failed,
                result={
                    "articles": result.articles,
                    "extractors": result.extractors,
                    "operations": result.operations,
                },
            )
        elif isinstance(result, EvaluationRunResult):
            updates.update(
                article_count=result.articles,
                processor_count=result.evaluators,
                total_operations=result.operations,
                completed_operations=result.operations,
                stored_operations=result.stored,
                skipped_operations=result.skipped,
                failed_operations=result.failed,
                result={
                    "articles": result.articles,
                    "evaluators": result.evaluators,
                    "operations": result.operations,
                },
            )
        completed = run.model_copy(update=updates)
        self.runs.update(completed)
        self._record_event(completed, "processing-run-completed")

    def _fail(self, run_id: UUID, exc: Exception) -> None:
        run = self._required_run(run_id)
        now = utc_now()
        failed = run.model_copy(
            update={
                "status": "failed",
                "error_message": str(exc) or exc.__class__.__name__,
                "finished_at": now,
                "updated_at": now,
            }
        )
        self.runs.update(failed)
        self._record_event(failed, "processing-run-failed")

    def _record_event(self, run: ProcessingRun, event_type: str) -> None:
        self.events.insert(
            WorkflowEvent(
                artefact_type="processing_run",
                artefact_id=run.id,
                event_type=event_type,
                payload={
                    "kind": run.kind,
                    "status": run.status,
                    "stored": run.stored_operations,
                    "skipped": run.skipped_operations,
                    "failed": run.failed_operations,
                },
            )
        )

    def _required_run(self, run_id: UUID) -> ProcessingRun:
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError(f"Processing run not found: {run_id}")
        return run


class ProcessingRunCoordinator:
    def __init__(self, service: ProcessingRunService):
        self.service = service
        self.service.interrupt_active_runs()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="editorial-processing"
        )
        self._lock = threading.Lock()
        self._future: Future[ProcessingResult | None] | None = None

    def start(
        self,
        kind: ProcessingKind,
        config_path: str | Path,
        options: ProcessingRunOptions | None = None,
    ) -> ProcessingRun:
        with self._lock:
            if self._future is not None and not self._future.done():
                raise ValueError("Another processing run is already active")
            active = self.service.runs.active()
            if active:
                raise ValueError(f"Processing run {active[0].id} is already active")
            run = self.service.create_run(kind, config_path, options)
            self._future = self._executor.submit(
                self.service.execute,
                run.id,
                None,
                raise_on_failure=False,
            )
            return run

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)


def _config_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
