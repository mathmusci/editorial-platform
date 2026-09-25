from __future__ import annotations

import json
import asyncio
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
from editorial.models import Review, ReviewDecision
from editorial.reviews import ReviewSubmissionService
from editorial.revisions import ReviewRevisionService
from editorial.optimisation_service import (
    generate_proposal,
    template_from_config,
    run_optimisation_request,
)
from starlette.concurrency import run_in_threadpool
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

from editorial.web.composition import CompositionWorkspace
from editorial.web.configuration_editor import Draft, TYPES
from editorial.web.files import FILE_TYPES, create_database, file_browser, selected_file
from editorial.publishing import MarkdownPublisher
from editorial.models import WorkflowEvent

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


def create_app(
    config_path: str | Path | None = None, db_path: str | Path | None = None
) -> FastAPI:
    config_path = Path(config_path) if config_path is not None else None
    db_path = Path(db_path) if db_path is not None else None
    if config_path is not None:
        db_path = db_path if db_path is not None else Path("editorial.sqlite")
    services = WorkspaceServices.build(config_path, db_path) if config_path else None
    composer = CompositionWorkspace(db_path) if services else None
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    deployment_path = Path.cwd().resolve()
    templates.env.filters["deployment_relative"] = lambda value: (
        os.path.relpath(Path(value).expanduser().resolve(), deployment_path)
        if value
        else ""
    )
    templates.env.filters["json_pretty"] = _json_pretty
    templates.env.filters["short_id"] = lambda value: str(value)[:8]
    templates.env.filters["duration"] = _format_duration

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if services:
            services.coordinator.shutdown()

    app = FastAPI(
        title=f"{services.config.publication.name} editorial workspace"
        if services
        else "Editorial workspace",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.workspace = services
    app.state.csrf_token = secrets.token_urlsafe(32)
    drafts: dict[str, Draft] = {}
    app.state.configuration_changed = False
    workspace_lock = asyncio.Lock()
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    @app.middleware("http")
    async def stable_workspace(request: Request, call_next):
        # Keep every request on one workspace, including awaited write operations.
        async with workspace_lock:
            if (
                services is None
                and request.url.path != "/workspace"
                and not request.url.path.startswith("/configuration/editor")
                and not request.url.path.startswith("/static/")
            ):
                if request.method in {"GET", "HEAD"}:
                    return RedirectResponse("/workspace", status_code=303)
                return Response(
                    "Open a workspace before submitting actions.", status_code=409
                )
            if (
                app.state.configuration_changed
                and request.method == "POST"
                and request.url.path != "/workspace"
                and not request.url.path.startswith("/configuration/editor")
            ):
                return Response(
                    "The configuration was saved. Open the workspace again to activate it before submitting actions.",
                    status_code=409,
                )
            return await call_next(request)

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
                "publication_name": services.config.publication.name
                if services
                else "Editorial",
                "workspace_loaded": services is not None,
                "configuration_changed": app.state.configuration_changed,
                "current_path": request.url.path,
                "status_code": status_code,
                "csrf_token": app.state.csrf_token,
                "active_config_path": services.config_path.resolve()
                if services
                else None,
                "active_db_path": services.db_path.resolve() if services else None,
                **context,
            },
        )

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/proposals", status_code=303)

    @app.get("/workspace", response_class=HTMLResponse)
    def workspace_selection(request: Request):
        return render(
            request,
            "workspace_selection.html",
            values={
                "config_path": str(services.config_path.resolve()) if services else "",
                "db_path": str(services.db_path.resolve())
                if services
                else str(db_path.resolve())
                if db_path
                else "",
            },
        )

    @app.post("/workspace")
    async def select_workspace(request: Request):
        nonlocal services, composer
        form = await review_form(request)
        if "cancel_creation" in form:
            return render(request, "workspace_selection.html", values=form)
        if "cancel_browser" in form:
            if form.get("creating"):
                return render(request, "new_database.html", values=form)
            return render(request, "workspace_selection.html", values=form)
        if "new_database" in form or "use_folder" in form:
            if "use_folder" in form:
                form["new_directory"] = form["use_folder"]
            form.setdefault("new_directory", str(deployment_path))
            form.setdefault("filename", "editorial.sqlite")
            return render(request, "new_database.html", values=form)
        if "browse" in form or "directory" in form or "selected_file" in form:
            field = form.get("browse", form.get("field", ""))
            try:
                if field not in FILE_TYPES:
                    raise ValueError("Unknown file type")
                if "selected_file" in form:
                    form[field] = str(selected_file(field, form["selected_file"]))
                    return render(request, "workspace_selection.html", values=form)
                directory = form.get("directory")
                if directory is None:
                    current = form.get(field, "")
                    directory = (
                        str(Path(current).expanduser().parent)
                        if current
                        else str(Path.cwd())
                    )
                    if form.get("creating") and form.get("new_directory"):
                        directory = form["new_directory"]
                picker = file_browser(field, directory)
            except (OSError, ValueError):
                return render(
                    request,
                    "workspace_selection.html",
                    values=form,
                    status_code=400,
                    error="Cannot browse that location or select that file. Check that it exists and is accessible.",
                )
            return render(request, "file_browser.html", values=form, picker=picker)
        if services and services.processing.runs.active():
            return render(
                request,
                "workspace_selection.html",
                values=form,
                status_code=409,
                error="Wait for the active processing run to finish before switching workspace.",
            )
        try:
            if "create_database" in form:
                selected_config, selected_db = create_database(
                    form.get("config_path", ""),
                    form.get("new_directory", ""),
                    form.get("filename", "").strip(),
                )
            else:
                selected_config, selected_db = _workspace_paths(form)
            replacement = WorkspaceServices.build(selected_config, selected_db)
        except FileExistsError:
            return render(
                request,
                "new_database.html",
                values=form,
                status_code=400,
                error="That name already exists. Choose a different filename; no file was overwritten.",
            )
        except (
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            sqlite3.Error,
            yaml.YAMLError,
        ):
            if "create_database" in form:
                return render(
                    request,
                    "new_database.html",
                    values=form,
                    status_code=400,
                    error="Cannot create database. Check the configuration, writable folder and .sqlite filename.",
                )
            return render(
                request,
                "workspace_selection.html",
                values=form,
                status_code=400,
                error="Cannot open workspace. Choose a valid publication configuration and an "
                "existing editorial SQLite database with no active processing runs. "
                "Check that both files are accessible.",
            )
        if services:
            services.coordinator.shutdown()
        services = replacement
        composer = CompositionWorkspace(selected_db)
        app.state.workspace = services
        app.state.configuration_changed = False
        app.state.csrf_token = secrets.token_urlsafe(32)
        app.title = f"{services.config.publication.name} editorial workspace"
        return RedirectResponse("/configuration", status_code=303)

    @app.post("/configuration/editor")
    async def start_configuration_editor(request: Request):
        form = await review_form(request)
        try:
            source = (
                None
                if form.get("new")
                else Path(
                    form.get("config_path")
                    or (str(services.config_path) if services else "")
                )
            )
            draft = Draft.open(source)
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            yaml.YAMLError,
        ):
            raise HTTPException(
                400, "Choose a valid configuration file to edit."
            ) from None
        token = secrets.token_urlsafe(24)
        if len(drafts) >= 32:
            drafts.pop(next(iter(drafts)))
        drafts[token] = draft
        return RedirectResponse(f"/configuration/editor/{token}", status_code=303)

    def editor_page(request, token, draft, *, error=None, saved=False, status_code=200):
        return render(
            request,
            "configuration_editor.html",
            token=token,
            error=error,
            saved=saved,
            status_code=status_code,
            **draft.context(),
        )

    @app.get("/configuration/editor/{token}")
    def configuration_editor(request: Request, token: str):
        if token not in drafts:
            raise HTTPException(404, "Draft expired. Reopen the configuration.")
        return editor_page(request, token, drafts[token])

    @app.post("/configuration/editor/{token}")
    async def update_configuration_editor(request: Request, token: str):
        form = await review_form(request)
        if token not in drafts:
            raise HTTPException(404, "Draft expired. Reopen the configuration.")
        draft = drafts[token]
        if form.get("revision") != str(draft.revision):
            return editor_page(
                request,
                token,
                draft,
                error="This draft changed in another tab. Review the latest fields before saving.",
                status_code=409,
            )
        action = form.get("action", "update")
        if action == "use" and draft.source:
            return render(
                request,
                "workspace_selection.html",
                values={
                    "config_path": str(draft.source),
                    "db_path": str(services.db_path) if services else "",
                },
            )
        if action == "discard":
            drafts.pop(token)
            return RedirectResponse(
                "/configuration" if services else "/workspace", status_code=303
            )
        draft.apply(form)
        if "filename" in form:
            draft.filename = form["filename"]
        draft.errors = {}
        try:
            parts = action.split(":")
            if parts[0] == "add" and parts[1] in TYPES:
                group = parts[1]
                kind = form.get(f"add_{group}", "")
                if kind not in TYPES[group]:
                    raise ValueError("Choose a supported type.")
                entry = {"type": kind, "enabled": True}
                if kind == "static":
                    entry["articles"] = []
                if kind in {
                    "llm_summary",
                    "llm_relevance",
                    "llm_summary_quality",
                }:
                    entry["provider"] = {"type": "fake"}
                draft.data.setdefault(group, []).append(entry)
            elif parts[0] == "remove" and parts[1] in TYPES:
                draft.data[parts[1]].pop(int(parts[2]))
            elif parts[0] in {"add_article", "remove_article"}:
                from editorial.web.configuration_editor import settings, set_setting

                entry = draft.data["providers"][int(parts[1])]
                if entry["type"] != "static":
                    raise ValueError("Select a static provider.")
                articles = settings(entry).get("articles", [])
                if parts[0] == "add_article":
                    articles.append({"title": ""})
                else:
                    articles.pop(int(parts[2]))
                set_setting(entry, "articles", articles)
            elif action in {"save", "save_as"}:
                if services and services.processing.runs.active():
                    raise ValueError(
                        "Wait for the active processing run to finish before saving."
                    )
                directory = draft.source.parent if draft.source else deployment_path
                filename = form.get("filename", "").strip()
                if not filename or Path(filename).name != filename:
                    raise ValueError(
                        "Enter a YAML filename without directory separators."
                    )
                destination = (
                    draft.source
                    if action == "save" and draft.source
                    else directory / filename
                )
                draft.save(
                    destination, overwrite=action == "save" and draft.source is not None
                )
                if services and destination.resolve() == services.config_path.resolve():
                    app.state.configuration_changed = True
                return editor_page(request, token, draft, saved=True)
        except FileExistsError:
            return editor_page(
                request,
                token,
                draft,
                error="That filename already exists. Choose another name for Save as.",
                status_code=400,
            )
        except (
            OSError,
            ValueError,
            TypeError,
            IndexError,
            KeyError,
            yaml.YAMLError,
        ) as exc:
            message = (
                str(exc)
                if isinstance(exc, ValueError) and not hasattr(exc, "errors")
                else "Unable to save. Check the file location and configuration fields."
            )
            return editor_page(request, token, draft, error=message, status_code=400)
        return editor_page(request, token, draft)

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
            options = (
                _processing_options(form) if kind in {"extract", "evaluate"} else None
            )
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

    @app.post("/proposals/generate")
    async def generate_issue(request: Request):
        await review_form(request)
        try:
            result, _proposal = await run_in_threadpool(
                generate_proposal,
                services.config,
                services.config_path,
                services.db_path,
            )
        except (ValueError, RuntimeError) as exc:
            return render(
                request,
                "proposals.html",
                status_code=400,
                proposals=services.proposals.list(),
                error=f"Proposal generation failed: {exc}",
            )
        return RedirectResponse(f"/proposals/{result.proposal_id}", status_code=303)

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

    async def review_form(request: Request) -> dict[str, str]:
        form = _parse_form(await request.body())
        if not secrets.compare_digest(form.get("csrf_token", ""), app.state.csrf_token):
            raise HTTPException(403, "Invalid form token")
        return form

    @app.get("/proposals/{proposal_id}/review", response_class=HTMLResponse)
    def new_review(request: Request, proposal_id: UUID):
        inspection = services.proposals.get(proposal_id)
        if inspection is None:
            raise HTTPException(404, "Issue proposal not found")
        return render(
            request, "review_form.html", inspection=inspection, values={}, error=None
        )

    @app.post("/proposals/{proposal_id}/review")
    async def submit_review(request: Request, proposal_id: UUID):
        form = await review_form(request)
        inspection = services.proposals.get(proposal_id)
        if inspection is None:
            raise HTTPException(404, "Issue proposal not found")
        try:
            review = Review(
                artefact_type="issue_proposal",
                artefact_id=proposal_id,
                reviewer=form.get("reviewer", "").strip(),
                decision=ReviewDecision(form.get("decision", "")),
                comments=form.get("comments", "").strip() or None,
                findings={"notes": form["findings"].strip()}
                if form.get("findings", "").strip()
                else {},
                recommendations={"notes": form["recommendations"].strip()}
                if form.get("recommendations", "").strip()
                else {},
            )
        except ValueError:
            return render(
                request,
                "review_form.html",
                status_code=400,
                inspection=inspection,
                values=form,
                error="Enter a reviewer name and select a valid decision.",
            )
        await run_in_threadpool(
            ReviewSubmissionService(services.db_path).submit, review
        )
        return RedirectResponse(f"/reviews/{review.id}", status_code=303)

    @app.post("/reviews/{review_id}/revise")
    async def revise_review(request: Request, review_id: UUID):
        form = await review_form(request)
        inspection = services.reviews.get(review_id)
        if inspection is None:
            raise HTTPException(404, "Review not found")
        try:
            overrides = {}
            for field in ("settings", "constraints", "goals", "preferences"):
                value = json.loads(form.get(field) or "{}")
                if not isinstance(value, dict):
                    raise ValueError(f"{field.capitalize()} must be a JSON object")
                overrides[field] = value
            revision_service = ReviewRevisionService(
                services.reviews.reviews,
                services.reviews.proposals,
                services.reviews.optimisation_requests,
                services.reviews.workflow_events,
            )
            revision = await run_in_threadpool(
                revision_service.create,
                review_id,
                template_from_config(services.config),
                created_by=form.get("created_by", "").strip() or None,
                **overrides,
            )
        except ValueError as exc:
            return render(
                request,
                "review.html",
                status_code=400,
                inspection=inspection,
                values=form,
                error=str(exc),
            )
        return RedirectResponse(
            f"/revision-requests/{revision.request.id}", status_code=303
        )

    def required_revision(request_id: UUID):
        revision = services.reviews.optimisation_requests.get(request_id)
        if revision is None or not revision.metadata.get("source_review_id"):
            raise HTTPException(404, "Revision request not found")
        return revision

    @app.get("/revision-requests/{request_id}", response_class=HTMLResponse)
    def revision_detail(request: Request, request_id: UUID):
        revision = required_revision(request_id)
        candidates = [
            p
            for p in services.reviews.proposals.list()
            if p.metadata.get("optimisation_request_id") == str(request_id)
        ]
        return render(
            request, "revision.html", revision=revision, candidates=candidates
        )

    @app.post("/revision-requests/{request_id}/run")
    async def run_revision(request: Request, request_id: UUID):
        await review_form(request)
        revision = required_revision(request_id)
        try:
            await run_in_threadpool(
                run_optimisation_request, revision, services.db_path
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(f"/revision-requests/{request_id}", status_code=303)

    @app.get("/reviews/{review_id}", response_class=HTMLResponse)
    def review_detail(request: Request, review_id: UUID) -> HTMLResponse:
        inspection = services.reviews.get(review_id)
        if inspection is None:
            raise HTTPException(status_code=404, detail="Review not found")
        return render(
            request, "review.html", inspection=inspection, values={}, error=None
        )

    @app.get("/proposals/{proposal_id}/compose", response_class=HTMLResponse)
    def composition_form(
        request: Request, proposal_id: UUID, parent: UUID | None = None
    ):
        try:
            context = composer.context(
                proposal_id, services.config.publication.name, parent
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return render(request, "composition.html", **context, error=None)

    @app.post("/proposals/{proposal_id}/compose")
    async def save_composition(request: Request, proposal_id: UUID):
        form = await review_form(request)
        try:
            parent = UUID(form["parent_id"]) if form.get("parent_id") else None
            context = composer.context(
                proposal_id, services.config.publication.name, parent
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            publication = await run_in_threadpool(composer.save, context, form)
        except ValueError as exc:
            context["values"] = form
            return render(
                request, "composition.html", status_code=400, **context, error=str(exc)
            )
        return RedirectResponse(f"/publications/{publication.id}", status_code=303)

    @app.post("/publications/{publication_id}/markdown")
    async def render_publication(request: Request, publication_id: UUID):
        await review_form(request)
        publication = composer.publications.get(publication_id)
        if publication is None:
            raise HTTPException(404, "Publication not found")
        content = MarkdownPublisher(composer.articles.list()).render(publication)
        composer.events.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-published",
                payload={"format": "markdown", "delivery": "browser-download"},
            )
        )
        return Response(
            content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="publication-{publication.id}.md"',
            },
        )

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


def _workspace_paths(form: dict[str, str]) -> tuple[Path, Path]:
    paths = []
    for key in ("config_path", "db_path"):
        value = form.get(key, "").strip()
        if not value:
            raise ValueError("Both paths are required")
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Choose a file")
        paths.append(path)
    config_path, db_path = paths
    load_publication_config(config_path)
    # Inspect without creating files or initialising repositories in another database.
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "articles" not in tables:
            raise ValueError("Not an editorial database")
        if "processing_runs" in tables:
            active = connection.execute(
                "SELECT 1 FROM processing_runs WHERE status IN ('queued', 'running') LIMIT 1"
            ).fetchone()
            if active:
                raise ValueError("Target database has an active run")
    return config_path, db_path


def _parse_form(body: bytes) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(
            body.decode("utf-8"), keep_blank_values=True
        ).items()
    }


def _processing_kind(value: str | None) -> ProcessingKind:
    if value not in {"ingest", "extract", "evaluate", "optimise"}:
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
