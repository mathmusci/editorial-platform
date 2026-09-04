from __future__ import annotations

import json
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from editorial.config import PublicationConfig, load_publication_config
from editorial.evaluators import describe_evaluator
from editorial.extractors import describe_extractor
from editorial.inspection import (
    ArticleInspectionService,
    ProposalComparisonService,
    ProposalInspectionService,
    PublicationInspectionService,
    ReviewInspectionService,
    WorkflowOverviewService,
)
from editorial.models import (
    ProcessingKind,
    ProcessingRun,
    ProcessingRunOptions,
    utc_now,
)
from editorial.processing import ProcessingRunCoordinator, ProcessingRunService
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

PACKAGE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class WorkspaceServices:
    config: PublicationConfig
    config_path: Path
    db_path: Path
    articles: ArticleInspectionService
    proposals: ProposalInspectionService
    proposal_comparison: ProposalComparisonService
    reviews: ReviewInspectionService
    publications: PublicationInspectionService
    workflows: WorkflowOverviewService
    processing: ProcessingRunService
    coordinator: ProcessingRunCoordinator

    @classmethod
    def build(cls, config_path: Path, db_path: Path) -> WorkspaceServices:
        config = load_publication_config(config_path)
        article_repository = SQLiteArticleRepository(db_path)
        extraction_repository = SQLiteExtractionRepository(db_path)
        evaluation_repository = SQLiteEvaluationRepository(db_path)
        proposal_repository = SQLiteIssueProposalRepository(db_path)
        request_repository = SQLiteOptimisationRequestRepository(db_path)
        review_repository = SQLiteReviewRepository(db_path)
        publication_repository = SQLitePublicationRepository(db_path)
        event_repository = SQLiteWorkflowEventRepository(db_path)

        proposals = ProposalInspectionService(
            proposals=proposal_repository,
            articles=article_repository,
            extractions=extraction_repository,
            evaluations=evaluation_repository,
            optimisation_requests=request_repository,
            workflow_events=event_repository,
            reviews=review_repository,
            publications=publication_repository,
        )
        processing = ProcessingRunService(db_path)
        return cls(
            config=config,
            config_path=config_path,
            db_path=db_path,
            articles=ArticleInspectionService(
                articles=article_repository,
                extractions=extraction_repository,
                evaluations=evaluation_repository,
                proposals=proposal_repository,
                publications=publication_repository,
                workflow_events=event_repository,
            ),
            proposals=proposals,
            proposal_comparison=ProposalComparisonService(proposals),
            reviews=ReviewInspectionService(
                reviews=review_repository,
                proposals=proposal_repository,
                optimisation_requests=request_repository,
                publications=publication_repository,
                workflow_events=event_repository,
            ),
            publications=PublicationInspectionService(
                publications=publication_repository,
                proposals=proposal_repository,
                optimisation_requests=request_repository,
                articles=article_repository,
                extractions=extraction_repository,
                evaluations=evaluation_repository,
                reviews=review_repository,
                workflow_events=event_repository,
            ),
            workflows=WorkflowOverviewService(
                articles=article_repository,
                extractions=extraction_repository,
                evaluations=evaluation_repository,
                proposals=proposal_repository,
                optimisation_requests=request_repository,
                reviews=review_repository,
                publications=publication_repository,
                workflow_events=event_repository,
            ),
            processing=processing,
            coordinator=ProcessingRunCoordinator(processing),
        )

    def workflow_for(self, proposal_id: UUID):
        return self.workflows.build(
            proposal_id,
            self.config.publication.name,
            [
                describe_extractor(item)
                for item in self.config.extractors
                if item.enabled
            ],
            [
                describe_evaluator(item)
                for item in self.config.evaluators
                if item.enabled
            ],
            config_path=self.config_path,
            db_path=self.db_path,
        )


def create_app(config_path: str | Path, db_path: str | Path) -> FastAPI:
    config_path = Path(config_path)
    db_path = Path(db_path)
    services = WorkspaceServices.build(config_path, db_path)
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["json_pretty"] = _json_pretty
    templates.env.filters["short_id"] = lambda value: str(value)[:8]
    templates.env.filters["duration"] = _format_duration

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        services.coordinator.shutdown()

    app = FastAPI(
        title=f"{services.config.publication.name} editorial workspace",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.workspace = services
    app.state.csrf_token = secrets.token_urlsafe(32)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    def render(
        request: Request,
        template: str,
        *,
        status_code: int = 200,
        **context: Any,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name=template,
            status_code=status_code,
            context={
                "publication_name": services.config.publication.name,
                "current_path": request.url.path,
                "status_code": status_code,
                "csrf_token": app.state.csrf_token,
                **context,
            },
        )

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/proposals", status_code=303)

    @app.get("/configuration", response_class=HTMLResponse)
    def configuration(request: Request) -> HTMLResponse:
        config_data = services.config.model_dump(mode="json", exclude={"base_path"})
        safe_config = _redact_sensitive(config_data)
        return render(
            request,
            "configuration.html",
            config=services.config,
            config_path=services.config_path.resolve(),
            db_path=services.db_path.resolve(),
            processor_groups=[
                ("Content providers", "providers", services.config.providers),
                ("Extractors", "extractors", services.config.extractors),
                ("Evaluators", "evaluators", services.config.evaluators),
                ("Publishers", "publishers", services.config.publishers),
            ],
            safe_settings={
                group: [_redact_sensitive(item.settings) for item in processors]
                for _label, group, processors in [
                    ("Content providers", "providers", services.config.providers),
                    ("Extractors", "extractors", services.config.extractors),
                    ("Evaluators", "evaluators", services.config.evaluators),
                    ("Publishers", "publishers", services.config.publishers),
                ]
            },
            normalized_yaml=yaml.safe_dump(
                safe_config,
                sort_keys=False,
                allow_unicode=True,
            ),
        )

    @app.get("/operations", response_class=HTMLResponse)
    def operation_list(request: Request) -> HTMLResponse:
        runs = services.processing.runs.list(limit=50)
        return render(
            request,
            "operations.html",
            runs=[_run_view(run) for run in runs],
            active_run=next((run for run in runs if run.active), None),
        )

    @app.post("/operations")
    async def start_operation(request: Request) -> RedirectResponse:
        form = _parse_form(await request.body())
        if not secrets.compare_digest(form.get("csrf_token", ""), app.state.csrf_token):
            raise HTTPException(status_code=403, detail="Invalid form token")
        try:
            kind = _processing_kind(form.get("kind"))
            options = _processing_options(form) if kind != "ingest" else None
            run = services.coordinator.start(kind, services.config_path, options)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/operations/{run.id}", status_code=303)

    @app.get("/operations/{run_id}", response_class=HTMLResponse)
    def operation_detail(request: Request, run_id: UUID) -> HTMLResponse:
        run = services.processing.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Processing run not found")
        return render(
            request,
            "operation.html",
            run=_run_view(run),
        )

    @app.get("/proposals", response_class=HTMLResponse)
    def proposal_list(request: Request) -> HTMLResponse:
        return render(
            request,
            "proposals.html",
            proposals=services.proposals.list(),
        )

    @app.get("/proposals/compare", response_class=HTMLResponse)
    def compare_proposals(
        request: Request,
        base: UUID = Query(...),
        candidate: UUID = Query(...),
    ) -> HTMLResponse:
        try:
            comparison = services.proposal_comparison.compare(base, candidate)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return render(
            request,
            "proposal_compare.html",
            comparison=comparison,
            proposals=services.proposals.list(),
        )

    @app.get("/proposals/{proposal_id}", response_class=HTMLResponse)
    def proposal_detail(request: Request, proposal_id: UUID) -> HTMLResponse:
        proposal = services.proposals.get(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="Issue proposal not found")
        return render(
            request,
            "proposal.html",
            inspection=proposal,
            workflow=services.workflow_for(proposal_id),
        )

    @app.get("/articles", response_class=HTMLResponse)
    def article_list(request: Request) -> HTMLResponse:
        return render(request, "articles.html", articles=services.articles.list())

    @app.get("/articles/{article_id}", response_class=HTMLResponse)
    def article_detail(request: Request, article_id: UUID) -> HTMLResponse:
        inspection = services.articles.get(article_id)
        if inspection is None:
            raise HTTPException(status_code=404, detail="Article not found")
        return render(request, "article.html", inspection=inspection)

    @app.get("/reviews", response_class=HTMLResponse)
    def review_list(request: Request) -> HTMLResponse:
        return render(request, "reviews.html", reviews=services.reviews.list())

    @app.get("/reviews/{review_id}", response_class=HTMLResponse)
    def review_detail(request: Request, review_id: UUID) -> HTMLResponse:
        inspection = services.reviews.get(review_id)
        if inspection is None:
            raise HTTPException(status_code=404, detail="Review not found")
        return render(request, "review.html", inspection=inspection)

    @app.get("/publications", response_class=HTMLResponse)
    def publication_list(request: Request) -> HTMLResponse:
        return render(
            request,
            "publications.html",
            publications=services.publications.list(),
        )

    @app.get("/publications/{publication_id}", response_class=HTMLResponse)
    def publication_detail(request: Request, publication_id: UUID) -> HTMLResponse:
        inspection = services.publications.get(publication_id)
        if inspection is None:
            raise HTTPException(status_code=404, detail="Publication not found")
        return render(
            request,
            "publication.html",
            inspection=inspection,
            article_count=sum(len(section.articles) for section in inspection.sections),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> HTMLResponse:
        return render(
            request,
            "error.html",
            status_code=exc.status_code,
            detail=exc.detail,
        )

    return app


def _json_pretty(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, indent=2, default=str, sort_keys=True)


def _parse_form(body: bytes) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(
            body.decode("utf-8"), keep_blank_values=True
        ).items()
    }


def _processing_kind(value: str | None) -> ProcessingKind:
    if value not in {"ingest", "extract", "evaluate"}:
        raise ValueError("Unknown processing operation")
    return value


def _processing_options(form: dict[str, str]) -> ProcessingRunOptions:
    raw_article_ids = re.split(r"[\s,]+", form.get("article_ids", "").strip())
    return ProcessingRunOptions(
        limit=_optional_integer(form.get("limit"), "limit"),
        offset=_optional_integer(form.get("offset"), "offset") or 0,
        article_ids=[UUID(value) for value in raw_article_ids if value],
        missing_only=form.get("missing_only") == "on",
        force=form.get("force") == "on",
    )


def _optional_integer(value: str | None, name: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _run_view(run: ProcessingRun) -> dict[str, Any]:
    end = run.finished_at or utc_now()
    elapsed = max((end - (run.started_at or run.created_at)).total_seconds(), 0)
    remaining = None
    if run.active and run.completed_operations and run.total_operations:
        remaining_operations = run.total_operations - run.completed_operations
        remaining = max(
            elapsed / run.completed_operations * remaining_operations,
            0,
        )
    return {
        "record": run,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
    }


def _format_duration(value: float | int | None) -> str:
    if value is None:
        return "Not available"
    seconds = max(round(value), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "*** redacted ***"
                if _sensitive_key(str(key))
                else _redact_sensitive(nested)
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if normalized.endswith("_env"):
        return False
    return any(
        part in {"password", "secret", "token", "api_key", "credential"}
        for part in (
            normalized,
            *normalized.split("_"),
        )
    )
