from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from editorial.cli_helpers import (
    parse_key_values,
    parse_payload,
    record_publication_created,
    record_publication_rendered,
    record_review_submitted,
    request_from_config,
    run_optimisation_request,
)
from editorial.config import load_publication_config
from editorial.engine import EditorialEngine
from editorial.evaluators import build_evaluator
from editorial.explain import (
    ArticleSelectionArticleNotFound,
    ArticleSelectionExplanation,
    ArticleSelectionExplanationService,
    EvaluationExplanation,
    EvaluationExplanationService,
    OptimisationRequestExplanation,
    OptimisationRequestExplanationService,
    PublicationExplanation,
    PublicationExplanationService,
    ProposalExplanation,
    ProposalExplanationService,
)
from editorial.extractors import build_extractor
from editorial.inspection import (
    ArticleInspection,
    ArticleInspectionService,
    EvaluationInspection,
    EvaluationInspectionService,
    ExtractionArtefactInspection,
    ExtractionInspectionService,
    ProposalInspection,
    ProposalInspectionService,
    PublicationInspection,
    PublicationInspectionService,
    ReviewInspection,
    ReviewInspectionService,
)
from editorial.models import (
    EditorialStatus,
    Review,
    ReviewDecision,
    WorkflowEvent,
)
from editorial.publishing import MarkdownPublisher, PublicationBuilder
from editorial.providers import build_provider
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

app = typer.Typer(help="Editorial processing platform CLI")
workflow_app = typer.Typer(help="Record and inspect workflow events")
optimisation_request_app = typer.Typer(help="Create and run optimisation requests")
review_app = typer.Typer(help="Create and inspect editorial reviews")
publication_app = typer.Typer(help="Create and inspect publication artefacts")
publish_app = typer.Typer(help="Render publications to output formats")
proposal_app = typer.Typer(help="Inspect issue proposals")
evaluation_app = typer.Typer(help="Inspect evaluations")
extraction_app = typer.Typer(help="Inspect extractions")
article_app = typer.Typer(help="Inspect articles")
explain_app = typer.Typer(help="Explain editorial artefacts")
app.add_typer(workflow_app, name="workflow")
app.add_typer(optimisation_request_app, name="optimisation-request")
app.add_typer(review_app, name="review")
app.add_typer(publication_app, name="publication")
app.add_typer(publish_app, name="publish")
app.add_typer(proposal_app, name="proposal")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(extraction_app, name="extraction")
app.add_typer(article_app, name="article")
app.add_typer(explain_app, name="explain")
console = Console()


def _proposal_inspection_service(db: Path) -> ProposalInspectionService:
    return ProposalInspectionService(
        proposals=SQLiteIssueProposalRepository(db),
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        evaluations=SQLiteEvaluationRepository(db),
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
        reviews=SQLiteReviewRepository(db),
        publications=SQLitePublicationRepository(db),
    )


def _evaluation_inspection_service(db: Path) -> EvaluationInspectionService:
    return EvaluationInspectionService(
        evaluations=SQLiteEvaluationRepository(db),
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
    )


def _extraction_inspection_service(db: Path) -> ExtractionInspectionService:
    return ExtractionInspectionService(
        extractions=SQLiteExtractionRepository(db),
        articles=SQLiteArticleRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
    )


def _article_inspection_service(db: Path) -> ArticleInspectionService:
    return ArticleInspectionService(
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        evaluations=SQLiteEvaluationRepository(db),
        proposals=SQLiteIssueProposalRepository(db),
        publications=SQLitePublicationRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
    )


def _publication_inspection_service(db: Path) -> PublicationInspectionService:
    return PublicationInspectionService(
        publications=SQLitePublicationRepository(db),
        proposals=SQLiteIssueProposalRepository(db),
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        evaluations=SQLiteEvaluationRepository(db),
        reviews=SQLiteReviewRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
    )


def _review_inspection_service(db: Path) -> ReviewInspectionService:
    return ReviewInspectionService(
        reviews=SQLiteReviewRepository(db),
        proposals=SQLiteIssueProposalRepository(db),
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
        publications=SQLitePublicationRepository(db),
        workflow_events=SQLiteWorkflowEventRepository(db),
    )


def _proposal_explanation_service(db: Path) -> ProposalExplanationService:
    return ProposalExplanationService(_proposal_inspection_service(db))


def _optimisation_request_explanation_service(
    db: Path,
) -> OptimisationRequestExplanationService:
    return OptimisationRequestExplanationService(
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
        proposals=SQLiteIssueProposalRepository(db),
    )


def _article_selection_explanation_service(
    db: Path,
) -> ArticleSelectionExplanationService:
    return ArticleSelectionExplanationService(
        proposals=SQLiteIssueProposalRepository(db),
        articles=SQLiteArticleRepository(db),
        extractions=SQLiteExtractionRepository(db),
        evaluations=SQLiteEvaluationRepository(db),
        optimisation_requests=SQLiteOptimisationRequestRepository(db),
    )


def _evaluation_explanation_service(db: Path) -> EvaluationExplanationService:
    return EvaluationExplanationService(
        evaluation_inspections=_evaluation_inspection_service(db),
        proposals=SQLiteIssueProposalRepository(db),
        publications=SQLitePublicationRepository(db),
    )


def _publication_explanation_service(db: Path) -> PublicationExplanationService:
    return PublicationExplanationService(_publication_inspection_service(db))


def _format_optional(value: object | None) -> str:
    return "" if value is None else str(value)


def _format_available(value: object | None) -> str:
    return "not available" if value is None else str(value)


def _format_scalar(value: object | None) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_label(value: object) -> str:
    text = str(value)
    if "_" not in text:
        return text
    return text.replace("_", " ").capitalize()


def _format_structured_value(value: object | None, *, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return "none"
        return "\n".join(
            f"{prefix}{_format_label(key)}: "
            f"{_format_structured_value(nested, indent=indent + 2).lstrip()}"
            for key, nested in sorted(value.items())
        )
    if isinstance(value, list | tuple | set):
        if not value:
            return "none"
        return "\n".join(
            f"{prefix}- {_format_structured_value(item, indent=indent + 2).lstrip()}"
            for item in value
        )
    return f"{prefix}{_format_scalar(value)}"


def _format_details(label: str, value: object | None) -> str:
    formatted = _format_structured_value(value)
    if "\n" in formatted:
        return f"{label}:\n{formatted}"
    return f"{label}: {formatted}"


def _without_metadata_keys(
    metadata: dict[str, Any],
    duplicated_keys: set[str],
) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key not in duplicated_keys}


def _format_evaluation_confidence(explanation: EvaluationExplanation) -> str:
    if explanation.confidence is None:
        return "not available"
    if explanation.provenance.evaluator_type == "deterministic":
        return f"{explanation.confidence} (rule-based)"
    return str(explanation.confidence)


def _preview(value: str | None, limit: int = 500) -> str:
    if not value:
        return "not available"
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _render_next_actions_table(actions: list[object]) -> None:
    table = Table(title="Next Actions", show_lines=True)
    table.add_column("Action")
    table.add_column("Command")
    for action in actions:
        table.add_row(action.label, action.command)
    console.print(table)


@app.command()
def ingest(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    providers = [
        build_provider(p, base_path=cfg.base_path) for p in cfg.providers if p.enabled
    ]
    result = EditorialEngine(SQLiteArticleRepository(db)).ingest(providers)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Fetched: {result.fetched}")
    console.print(f"Added: {result.added}")
    console.print(f"Duplicates in source: {result.duplicates_in_source}")
    console.print(f"Already in database: {result.already_in_database}")


@app.command()
def extract(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    extractors = [build_extractor(e) for e in cfg.extractors if e.enabled]
    result = EditorialEngine(
        SQLiteArticleRepository(db), SQLiteExtractionRepository(db)
    ).extract(extractors)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Articles: {result.articles}")
    console.print(f"Extractors: {result.extractors}")
    console.print(f"Stored extractions: {result.stored}")


@app.command()
def evaluate(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    evaluators = [build_evaluator(e) for e in cfg.evaluators if e.enabled]
    result = EditorialEngine(
        SQLiteArticleRepository(db),
        SQLiteExtractionRepository(db),
        SQLiteEvaluationRepository(db),
    ).evaluate(evaluators)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Articles: {result.articles}")
    console.print(f"Evaluators: {result.evaluators}")
    console.print(f"Stored evaluations: {result.stored}")


@app.command()
def optimise(
    config: Path = typer.Option(..., "--config", "-c"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    cfg = load_publication_config(config)
    request = request_from_config(config, metadata={"source": "editorial optimise"})
    SQLiteOptimisationRequestRepository(db).insert(request)
    result, proposal = run_optimisation_request(request, db)
    console.print(f"[bold]Publication:[/bold] {cfg.publication.name}")
    console.print(f"Optimiser: {result.optimiser}")
    console.print(f"Optimisation request: {request.id}")
    console.print(f"Selected articles: {result.selected_articles}")
    console.print(f"Objective value: {result.objective_value}")
    if proposal is not None:
        for constraint in proposal.constraint_results:
            console.print(
                f"- {constraint.name}: satisfied={constraint.satisfied}, penalty={constraint.penalty}"
            )


@app.command("list")
def list_articles(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    status: EditorialStatus | None = typer.Option(None, "--status"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    articles = SQLiteArticleRepository(db).list(status=status, limit=limit)
    table = Table(title="Articles")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("URL")
    for a in articles:
        table.add_row(
            a.status.value, a.source or "", a.title, str(a.url) if a.url else ""
        )
    console.print(table)


@explain_app.command("proposal")
def explain_proposal(
    proposal_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    explanation = _proposal_explanation_service(db).get(proposal_id)
    if explanation is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)
    _render_proposal_explanation(explanation)


@explain_app.command("optimisation-request")
def explain_optimisation_request(
    request_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    explanation = _optimisation_request_explanation_service(db).get(request_id)
    if explanation is None:
        console.print(f"Optimisation request not found: {request_id}")
        raise typer.Exit(1)
    _render_optimisation_request_explanation(explanation)


@explain_app.command("article-selection")
def explain_article_selection(
    proposal_id: UUID = typer.Argument(...),
    article_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    try:
        explanation = _article_selection_explanation_service(db).get(
            proposal_id, article_id
        )
    except ArticleSelectionArticleNotFound:
        console.print(f"Article not found: {article_id}")
        raise typer.Exit(1) from None
    if explanation is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)
    _render_article_selection_explanation(explanation)


@explain_app.command("evaluation")
def explain_evaluation(
    evaluation_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    explanation = _evaluation_explanation_service(db).get(evaluation_id)
    if explanation is None:
        console.print(f"Evaluation not found: {evaluation_id}")
        raise typer.Exit(1)
    _render_evaluation_explanation(explanation)


@explain_app.command("publication")
def explain_publication(
    publication_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    explanation = _publication_explanation_service(db).get(publication_id)
    if explanation is None:
        console.print(f"Publication not found: {publication_id}")
        raise typer.Exit(1)
    _render_publication_explanation(explanation)


def _render_publication_explanation(explanation: PublicationExplanation) -> None:
    identity = explanation.identity
    details = "\n".join(
        [
            f"[bold]Publication:[/bold] {identity.publication_id}",
            f"[bold]Title:[/bold] {identity.title}",
            f"[bold]Subtitle:[/bold] {_format_available(identity.subtitle)}",
            f"[bold]Created:[/bold] {identity.created_at.isoformat()}",
            f"[bold]Issue proposal:[/bold] {identity.proposal_id}",
            f"[bold]Optimisation request:[/bold] {_format_available(identity.optimisation_request_id)}",
            f"[bold]Status:[/bold] {_format_available(identity.status)}",
        ]
    )
    console.print(Panel(details, title="Publication Identity", expand=False))
    console.print(
        Panel(explanation.editorial_summary, title="Editorial Summary", expand=False)
    )
    _render_publication_explanation_workflow(explanation)
    _render_publication_explanation_composition(explanation)
    _render_publication_explanation_evidence(explanation)
    console.print(
        Panel(explanation.interpretation, title="Interpretation", expand=False)
    )
    console.print(
        Panel(
            "\n".join(f"- {item}" for item in explanation.limitations.items),
            title="Limitations",
            expand=False,
        )
    )
    _render_publication_explanation_related(explanation)
    _render_publication_explanation_next_actions(explanation)


def _render_publication_explanation_workflow(
    explanation: PublicationExplanation,
) -> None:
    workflow = explanation.evidence.workflow
    if not workflow.events:
        console.print(Panel("No workflow events recorded.", title="Workflow"))
        return
    table = Table(title="Editorial Workflow")
    table.add_column("Event")
    for event in workflow.events:
        table.add_row(event)
    console.print(table)


def _render_publication_explanation_composition(
    explanation: PublicationExplanation,
) -> None:
    composition = explanation.composition
    rows = {
        "Section count": composition.section_count,
        "Section titles": ", ".join(composition.section_titles)
        if composition.section_titles
        else "none",
        "Article count": composition.article_count,
        "Sources represented": composition.source_counts,
        "Total reading minutes": _format_available(composition.total_reading_minutes),
        "Average relevance score": _format_available(
            composition.average_relevance_score
        ),
        "Missing evaluations": composition.missing_evaluation_count,
        "Missing reading time": composition.missing_reading_time_count,
    }
    _render_key_value_table("Publication Composition", rows)


def _render_publication_explanation_evidence(
    explanation: PublicationExplanation,
) -> None:
    context = explanation.evidence.editorial_context
    rows = {
        "Summary": explanation.evidence.summary,
        "Proposal objective value": _format_available(context.proposal_objective_value),
        "Satisfied constraints": context.satisfied_constraint_count,
        "Failed constraints": context.failed_constraint_count,
        "Largest penalties": (
            ", ".join(
                f"{name}: {penalty}" for name, penalty in context.largest_penalties
            )
            if context.largest_penalties
            else "none"
        ),
        "Review decisions": ", ".join(context.review_decisions)
        if context.review_decisions
        else "none",
        "Review comments": " | ".join(context.review_comments)
        if context.review_comments
        else "none",
        "Additional metadata": _without_metadata_keys(
            context.metadata,
            {
                "article_count",
                "objective_value",
                "optimiser",
                "proposal_id",
            },
        )
        or None,
    }
    _render_key_value_table("Editorial Evidence", rows)


def _render_publication_explanation_related(
    explanation: PublicationExplanation,
) -> None:
    table = Table(title="Related Artefacts", show_lines=True)
    table.add_column("Type")
    table.add_column("Values")
    for key, values in explanation.related_artefacts.items():
        table.add_row(_format_label(key), "\n".join(values))
    console.print(table)


def _render_publication_explanation_next_actions(
    explanation: PublicationExplanation,
) -> None:
    _render_next_actions_table(explanation.next_actions)


def _render_evaluation_explanation(explanation: EvaluationExplanation) -> None:
    identity = "\n".join(
        [
            f"[bold]Evaluation:[/bold] {explanation.evaluation_id}",
            f"[bold]Article:[/bold] {explanation.article_id}",
            f"[bold]Article title:[/bold] {_format_available(explanation.article_title)}",
            f"[bold]Article source:[/bold] {_format_available(explanation.article_source)}",
            f"[bold]Evaluator:[/bold] {explanation.evaluator}",
            f"[bold]Evaluator version:[/bold] {_format_available(explanation.evaluator_version)}",
            f"[bold]Kind:[/bold] {explanation.kind}",
            f"[bold]Created:[/bold] {explanation.created_at.isoformat()}",
        ]
    )
    console.print(Panel(identity, title="Evaluation Identity", expand=False))
    outcome = "\n".join(
        [
            explanation.outcome_summary,
            f"Score: {_format_available(explanation.score)}",
            f"Confidence: {_format_evaluation_confidence(explanation)}",
            f"Rationale: {_format_available(explanation.rationale)}",
            f"Decision: {_format_available(explanation.decision)}",
        ]
    )
    console.print(Panel(outcome, title="Outcome", expand=False))
    _render_evaluation_explanation_evidence(explanation)
    _render_evaluation_explanation_provenance(explanation)
    _render_evaluation_explanation_interpretation(explanation)
    _render_evaluation_explanation_limitations(explanation)
    _render_evaluation_explanation_related(explanation)
    _render_evaluation_explanation_next_actions(explanation)


def _render_evaluation_explanation_evidence(
    explanation: EvaluationExplanation,
) -> None:
    if not explanation.evidence:
        console.print(Panel("No evidence recorded.", title="Evidence"))
        return

    table = Table(title="Evidence", show_lines=True)
    table.add_column("Type")
    table.add_column("Kind")
    table.add_column("Source")
    table.add_column("Highlights")
    for evidence in explanation.evidence:
        table.add_row(
            evidence.evidence_type,
            evidence.kind,
            evidence.source,
            _format_structured_value(evidence.highlights),
        )
    console.print(table)


def _render_evaluation_explanation_provenance(
    explanation: EvaluationExplanation,
) -> None:
    if not explanation.provenance.fields:
        message = (
            "AI provenance is not applicable for this deterministic evaluator."
            if explanation.provenance.evaluator_type == "deterministic"
            else "No provenance recorded."
        )
        console.print(Panel(message, title="Provenance"))
        return

    table = Table(title="Provenance")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("evaluator_type", explanation.provenance.evaluator_type)
    for key, value in sorted(explanation.provenance.fields.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


def _render_evaluation_explanation_interpretation(
    explanation: EvaluationExplanation,
) -> None:
    details = [explanation.interpretation.summary]
    if explanation.interpretation.confidence_note:
        details.append(explanation.interpretation.confidence_note)
    console.print(Panel("\n".join(details), title="Interpretation", expand=False))


def _render_evaluation_explanation_limitations(
    explanation: EvaluationExplanation,
) -> None:
    console.print(
        Panel(
            "\n".join(f"- {limitation}" for limitation in explanation.limitations),
            title="Limitations",
            expand=False,
        )
    )


def _render_evaluation_explanation_related(
    explanation: EvaluationExplanation,
) -> None:
    console.print(
        Panel(
            "\n".join(
                [
                    f"Article: {explanation.article_id}",
                    f"Title: {_format_available(explanation.article_title)}",
                ]
            ),
            title="Related Article",
            expand=False,
        )
    )
    for proposal in explanation.related_proposals:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"Proposal: {proposal.proposal_id}",
                        f"Optimiser: {proposal.optimiser}",
                        f"Objective: {proposal.objective_value}",
                    ]
                ),
                title="Related Proposal",
                expand=False,
            )
        )
    for publication in explanation.related_publications:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"Publication: {publication.publication_id}",
                        f"Title: {publication.title}",
                        f"Proposal: {publication.proposal_id}",
                    ]
                ),
                title="Related Publication",
                expand=False,
            )
        )


def _render_evaluation_explanation_next_actions(
    explanation: EvaluationExplanation,
) -> None:
    _render_next_actions_table(explanation.next_actions)


def _render_article_selection_explanation(
    explanation: ArticleSelectionExplanation,
) -> None:
    identity = "\n".join(
        [
            f"[bold]Proposal:[/bold] {explanation.proposal_id}",
            f"[bold]Article:[/bold] {explanation.article_id}",
            f"[bold]Title:[/bold] {explanation.article_title}",
            f"[bold]Source:[/bold] {_format_available(explanation.article_source)}",
            f"[bold]URL:[/bold] {_format_available(explanation.article_url)}",
            f"[bold]Optimisation request:[/bold] {_format_available(explanation.optimisation_request_id)}",
            f"[bold]Optimiser:[/bold] {explanation.optimiser}",
            f"[bold]Proposal objective value:[/bold] {explanation.proposal_objective_value}",
        ]
    )
    console.print(Panel(identity, title="Article Selection Identity", expand=False))
    console.print(
        Panel(
            explanation.outcome.status,
            title="Selection Outcome",
            expand=False,
        )
    )
    console.print(
        Panel(
            explanation.outcome.explanation,
            title="Deterministic Explanation",
            expand=False,
        )
    )
    if not explanation.outcome.included:
        console.print(
            Panel(
                "The stored proposal does not record the exact exclusion reason.",
                title="Exclusion Caveat",
                expand=False,
            )
        )
    _render_article_selection_evidence(explanation)
    _render_article_selection_proposal_context(explanation)
    _render_article_selection_constraints(explanation)
    _render_article_selection_next_actions(explanation)


def _render_article_selection_evidence(
    explanation: ArticleSelectionExplanation,
) -> None:
    if not explanation.evidence:
        console.print(
            Panel(
                "No extraction or evaluation evidence is available.",
                title="Article Evidence",
            )
        )
        return

    table = Table(title="Article Evidence", show_lines=True)
    table.add_column("Type")
    table.add_column("Kind")
    table.add_column("Producer")
    table.add_column("Details")
    for evidence in explanation.evidence:
        details = []
        if evidence.evidence_type == "evaluation":
            if evidence.score is not None:
                details.append(f"Score: {evidence.score}")
            if evidence.confidence is not None:
                details.append(f"Confidence: {evidence.confidence}")
            if evidence.rationale:
                details.append(f"Rationale: {evidence.rationale}")
        if evidence.highlights:
            details.append(_format_details("Highlights", evidence.highlights))
        table.add_row(
            evidence.evidence_type,
            evidence.kind,
            evidence.producer,
            "\n".join(details) if details else "No details recorded.",
        )
    console.print(table)
    rationales = [
        evidence.rationale for evidence in explanation.evidence if evidence.rationale
    ]
    for rationale in rationales:
        console.print(Panel(rationale, title="Rationale", expand=False))


def _render_article_selection_proposal_context(
    explanation: ArticleSelectionExplanation,
) -> None:
    context = explanation.proposal_context
    rows = {
        "Selected article count": context.selected_article_count,
        "Objective value": context.objective_value,
        "Satisfied constraints": context.satisfied_constraint_count,
        "Failed constraints": context.failed_constraint_count,
        "Largest penalties": (
            ", ".join(
                f"{name}: {penalty}" for name, penalty in context.largest_penalties
            )
            if context.largest_penalties
            else "none"
        ),
        "Sources represented": context.source_counts,
        "Article source represented": _format_available(
            context.article_source_represented
        ),
    }
    _render_key_value_table("Proposal Context", rows)


def _render_article_selection_constraints(
    explanation: ArticleSelectionExplanation,
) -> None:
    if not explanation.constraint_context:
        console.print(
            Panel(
                "No relevant proposal constraints were recorded.",
                title="Constraint Context",
            )
        )
        return

    table = Table(title="Constraint Context", show_lines=True)
    table.add_column("Constraint")
    table.add_column("Details")
    for constraint in explanation.constraint_context:
        details = "\n".join(
            [
                f"Kind: {constraint.kind}",
                f"Satisfied: {constraint.satisfied}",
                f"Value: {_format_available(constraint.value)}",
                f"Target: {_format_available(constraint.target)}",
                f"Penalty: {constraint.penalty}",
                constraint.interpretation,
            ]
        )
        table.add_row(constraint.name, details)
    console.print(table)


def _render_article_selection_next_actions(
    explanation: ArticleSelectionExplanation,
) -> None:
    _render_next_actions_table(explanation.next_actions)


def _render_optimisation_request_explanation(
    explanation: OptimisationRequestExplanation,
) -> None:
    identity = "\n".join(
        [
            f"[bold]Optimisation request:[/bold] {explanation.request_id}",
            f"[bold]Created:[/bold] {explanation.created_at.isoformat()}",
            f"[bold]Publication:[/bold] {_format_available(explanation.publication)}",
            f"[bold]Strategy:[/bold] {explanation.strategy}",
            f"[bold]Created by:[/bold] {_format_available(explanation.created_by)}",
        ]
    )
    console.print(Panel(identity, title="Optimisation Request", expand=False))
    console.print(
        Panel(explanation.editorial_summary, title="Editorial Summary", expand=False)
    )
    _render_optimisation_settings(explanation)
    _render_optimisation_json_inputs(explanation)
    _render_linked_proposals(explanation)
    _render_optimisation_balance(explanation)
    _render_optimisation_outcome(explanation)
    _render_optimisation_next_actions(explanation)


def _render_optimisation_settings(
    explanation: OptimisationRequestExplanation,
) -> None:
    if not explanation.settings:
        console.print(Panel("No settings recorded.", title="Settings"))
        return

    table = Table(title="Settings", show_lines=True)
    table.add_column("Setting")
    table.add_column("Details")
    for setting in explanation.settings:
        table.add_row(
            setting.name,
            "\n".join(
                [
                    _format_details("Value", setting.value),
                    setting.explanation,
                ]
            ),
        )
    console.print(table)
    custom_settings = [
        setting.name
        for setting in explanation.settings
        if setting.explanation
        == "Custom setting recorded for this optimisation request."
    ]
    if custom_settings:
        console.print(
            Panel(
                (
                    "Custom setting recorded for this optimisation request.\n"
                    f"Settings: {', '.join(custom_settings)}"
                ),
                title="Custom Settings",
                expand=False,
            )
        )


def _render_optimisation_json_inputs(
    explanation: OptimisationRequestExplanation,
) -> None:
    for title, values in [
        ("Constraints", explanation.constraints),
        ("Goals", explanation.goals),
        ("Preferences", explanation.preferences),
    ]:
        if values:
            _render_key_value_table(title, values)
        else:
            console.print(Panel(f"No {title.lower()} recorded.", title=title))


def _render_linked_proposals(
    explanation: OptimisationRequestExplanation,
) -> None:
    if not explanation.linked_proposals:
        console.print(
            Panel(
                "No IssueProposal linked to this optimisation request was found.",
                title="Linked Proposals",
            )
        )
        return

    table = Table(title="Linked Proposals", show_lines=True)
    table.add_column("Proposal ID", no_wrap=True)
    table.add_column("Details")
    for proposal in explanation.linked_proposals:
        details = "\n".join(
            [
                f"Created: {proposal.created_at.isoformat()}",
                f"Optimiser: {proposal.optimiser}",
                f"Selected articles: {proposal.selected_article_count}",
                f"Objective value: {proposal.objective_value}",
                f"Satisfied constraints: {proposal.satisfied_constraint_count}",
                f"Failed constraints: {proposal.failed_constraint_count}",
                f"Total penalty: {proposal.total_penalty}",
                f"Largest penalty: {_format_available(proposal.largest_penalty_name)}",
            ]
        )
        table.add_row(str(proposal.proposal_id), details)
    console.print(table)

    for proposal in explanation.linked_proposals:
        if not proposal.ordered_penalties:
            continue
        penalty_table = Table(title=f"Penalties for {proposal.proposal_id}")
        penalty_table.add_column("Constraint")
        penalty_table.add_column("Penalty", justify="right")
        for name, penalty in proposal.ordered_penalties:
            penalty_table.add_row(name, str(penalty))
        console.print(penalty_table)


def _render_optimisation_balance(
    explanation: OptimisationRequestExplanation,
) -> None:
    console.print(Panel(explanation.balance.summary, title="What Was Asked To Balance"))


def _render_optimisation_outcome(
    explanation: OptimisationRequestExplanation,
) -> None:
    console.print(Panel(explanation.outcome.summary, title="What Happened"))


def _render_optimisation_next_actions(
    explanation: OptimisationRequestExplanation,
) -> None:
    _render_next_actions_table(explanation.next_actions)


def _render_proposal_explanation(explanation: ProposalExplanation) -> None:
    identity = "\n".join(
        [
            f"[bold]Proposal:[/bold] {explanation.proposal_id}",
            f"[bold]Created:[/bold] {explanation.created_at.isoformat()}",
            f"[bold]Optimisation request:[/bold] {_format_available(explanation.optimisation_request_id)}",
            f"[bold]Publication:[/bold] {_format_available(explanation.publication_name)}",
            f"[bold]Optimiser:[/bold] {explanation.optimiser}",
            f"[bold]Selected articles:[/bold] {explanation.selected_article_count}",
            f"[bold]Objective value:[/bold] {explanation.objective_value}",
        ]
    )
    console.print(Panel(identity, title="Proposal Identity", expand=False))
    console.print(
        Panel(
            explanation.editorial_summary,
            title="Editorial Summary",
            expand=False,
        )
    )
    _render_explanation_constraints(explanation)
    _render_penalty_breakdown(explanation)
    _render_explained_articles(explanation)
    _render_trade_off_summary(explanation)
    _render_next_actions(explanation)


def _render_explanation_constraints(explanation: ProposalExplanation) -> None:
    if not explanation.constraints:
        console.print(
            Panel("No constraint results were recorded.", title="Constraints")
        )
        return

    console.print("[bold]Constraint Explanation[/bold]")
    for constraint in explanation.constraints:
        details = "\n".join(
            [
                f"Kind: {constraint.kind}",
                f"Satisfied: {constraint.satisfied}",
                f"Value: {_format_available(constraint.value)}",
                f"Target: {_format_available(constraint.target)}",
                f"Penalty: {constraint.penalty}",
                f"Message: {_format_available(constraint.message)}",
                constraint.explanation,
            ]
        )
        console.print(Panel(details, title=constraint.name, expand=False))


def _render_penalty_breakdown(explanation: ProposalExplanation) -> None:
    breakdown = explanation.penalty_breakdown
    summary = "\n".join(
        [
            f"[bold]Total penalty:[/bold] {breakdown.total_penalty}",
            f"[bold]Largest penalty:[/bold] {_format_available(breakdown.largest_penalty_name)}",
            f"[bold]Failed constraints:[/bold] {', '.join(breakdown.failed_constraints) if breakdown.failed_constraints else 'none'}",
            f"[bold]Zero-penalty constraints:[/bold] {', '.join(breakdown.zero_penalty_constraints) if breakdown.zero_penalty_constraints else 'none'}",
            f"[bold]Objective note:[/bold] {_format_available(breakdown.objective_note)}",
        ]
    )
    console.print(Panel(summary, title="Penalty Breakdown", expand=False))

    if not breakdown.ordered_constraints:
        return
    table = Table(title="Penalties by Constraint")
    table.add_column("Constraint")
    table.add_column("Penalty", justify="right")
    table.add_column("Satisfied")
    for constraint in breakdown.ordered_constraints:
        table.add_row(
            constraint.name,
            str(constraint.penalty),
            str(constraint.satisfied),
        )
    console.print(table)


def _render_explained_articles(explanation: ProposalExplanation) -> None:
    if not explanation.articles:
        console.print(Panel("No selected articles found.", title="Selected Articles"))
        return

    console.print("[bold]Selected Articles[/bold]")
    for article in explanation.articles:
        details = "\n".join(
            [
                f"[bold]Title:[/bold] {article.title}",
                f"[bold]Source:[/bold] {_format_available(article.source)}",
                f"[bold]URL:[/bold] {_format_available(article.url)}",
                f"[bold]Reading time:[/bold] {_format_available(article.reading_minutes)}",
                f"[bold]Relevance score:[/bold] {_format_available(article.relevance_score)}",
                f"[bold]Relevance rationale:[/bold] {_format_available(article.relevance_rationale)}",
                f"[bold]Article ID:[/bold] {article.article_id}",
                "[bold]Recorded evidence:[/bold]",
                article.explanation,
            ]
        )
        console.print(Panel(details, title=article.title, expand=False))


def _render_trade_off_summary(explanation: ProposalExplanation) -> None:
    trade_offs = explanation.trade_off_summary
    details = "\n".join(
        [
            trade_offs.summary,
            f"Total reading minutes: {_format_available(trade_offs.total_reading_minutes)}",
            f"Average relevance score: {_format_available(trade_offs.average_relevance_score)}",
            f"Missing evaluations: {trade_offs.missing_evaluation_count}",
            f"Missing reading-time data: {trade_offs.missing_reading_time_count}",
            _format_details("Sources represented", trade_offs.source_counts),
        ]
    )
    console.print(Panel(details, title="Trade-Off Summary", expand=False))


def _render_next_actions(explanation: ProposalExplanation) -> None:
    _render_next_actions_table(explanation.next_actions)


@article_app.command("list")
def article_list(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    articles = _article_inspection_service(db).list(limit=limit)
    if not articles:
        console.print("No articles found.")
        return

    table = Table(title="Articles", show_lines=True)
    table.add_column("Article ID", no_wrap=True)
    table.add_column("Details")
    for article in articles:
        details = "\n".join(
            [
                f"Title: {article.title}",
                f"Source: {article.source or 'not available'}",
                f"Status: {article.status}",
                f"Published: {_format_available(article.published_at.isoformat() if article.published_at else None)}",
                f"URL: {article.url or 'not available'}",
                f"Extractions: {article.extraction_count}",
                f"Evaluations: {article.evaluation_count}",
            ]
        )
        table.add_row(str(article.article_id), details)
    console.print(table)


@article_app.command("show")
def article_show(
    article_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _article_inspection_service(db).get(article_id)
    if inspection is None:
        console.print(f"Article not found: {article_id}")
        raise typer.Exit(1)
    _render_article_inspection(inspection)


def _render_article_inspection(inspection: ArticleInspection) -> None:
    article = inspection.article
    details = "\n".join(
        [
            f"[bold]Article:[/bold] {article.id}",
            f"[bold]Title:[/bold] {article.title}",
            f"[bold]Source:[/bold] {_format_available(article.source)}",
            f"[bold]Status:[/bold] {article.status.value}",
            f"[bold]Authors:[/bold] {', '.join(article.authors) if article.authors else 'not available'}",
            f"[bold]URL:[/bold] {_format_available(article.url)}",
            f"[bold]Published:[/bold] {_format_available(article.published_at.isoformat() if article.published_at else None)}",
        ]
    )
    console.print(Panel(details, title="Article", expand=False))
    console.print(Panel(_preview(article.summary), title="Summary", expand=False))
    console.print(
        Panel(_preview(article.content), title="Content Preview", expand=False)
    )
    _render_article_metadata(inspection)
    _render_article_extractions(inspection)
    _render_article_evaluations(inspection)
    _render_article_proposals(inspection)
    _render_article_publications(inspection)
    _render_article_workflow_events(inspection)


def _render_article_metadata(inspection: ArticleInspection) -> None:
    if not inspection.article.metadata:
        console.print(Panel("No metadata stored.", title="Metadata"))
        return

    table = Table(title="Metadata")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(inspection.article.metadata.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


def _render_article_extractions(inspection: ArticleInspection) -> None:
    if not inspection.extractions:
        console.print(Panel("No extractions found.", title="Extractions"))
        return

    table = Table(title="Extractions", show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Details")
    for item in inspection.extractions:
        extraction = item.extraction
        details = [
            f"Extractor: {extraction.extractor}",
            f"Version: {_format_available(extraction.extractor_version)}",
            f"Kind: {extraction.kind}",
            f"Created: {extraction.created_at.isoformat()}",
        ]
        if item.payload_highlights:
            details.append(_format_details("Highlights", item.payload_highlights))
        if item.ai_provenance:
            details.append(_format_details("AI provenance", item.ai_provenance))
        if not item.payload_highlights:
            details.append(_format_details("Payload", extraction.payload))
        table.add_row(str(extraction.id), "\n".join(details))
    console.print(table)


def _render_article_evaluations(inspection: ArticleInspection) -> None:
    if not inspection.evaluations:
        console.print(Panel("No evaluations found.", title="Evaluations"))
        return

    table = Table(title="Evaluations", show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Details")
    for item in inspection.evaluations:
        evaluation = item.evaluation
        details = [
            f"Evaluator: {evaluation.evaluator}",
            f"Version: {_format_available(evaluation.evaluator_version)}",
            f"Kind: {evaluation.kind}",
            f"Score: {_format_available(evaluation.score)}",
            f"Confidence: {_format_available(evaluation.confidence)}",
            f"Rationale: {_format_available(evaluation.rationale)}",
        ]
        if item.ai_provenance:
            details.append(_format_details("AI provenance", item.ai_provenance))
        table.add_row(str(evaluation.id), "\n".join(details))
    console.print(table)


def _render_article_proposals(inspection: ArticleInspection) -> None:
    if not inspection.proposals:
        console.print(Panel("No proposals found.", title="Proposals"))
        return

    table = Table(title="Proposals", show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Details")
    for proposal in inspection.proposals:
        details = "\n".join(
            [
                f"Created: {proposal.created_at.isoformat()}",
                f"Optimiser: {proposal.optimiser}",
                f"Objective: {proposal.objective_value}",
            ]
        )
        table.add_row(str(proposal.id), details)
    console.print(table)


def _render_article_publications(inspection: ArticleInspection) -> None:
    if not inspection.publications:
        console.print(Panel("No publications found.", title="Publications"))
        return

    table = Table(title="Publications", show_lines=True)
    table.add_column("ID", no_wrap=True)
    table.add_column("Details")
    for publication in inspection.publications:
        details = "\n".join(
            [
                f"Created: {publication.created_at.isoformat()}",
                f"Title: {publication.title}",
                f"Proposal: {publication.proposal_id}",
            ]
        )
        table.add_row(str(publication.id), details)
    console.print(table)


def _render_article_workflow_events(inspection: ArticleInspection) -> None:
    if not inspection.workflow_events:
        console.print(Panel("No workflow events found.", title="Workflow"))
        return

    table = Table(title="Workflow")
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in inspection.workflow_events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


@proposal_app.command("list")
def proposal_list(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    proposals = _proposal_inspection_service(db).list(limit=limit)
    if not proposals:
        console.print("No proposals found.")
        return

    table = Table(title="Issue Proposals", show_lines=True)
    table.add_column("Proposal ID", no_wrap=True)
    table.add_column("Details")
    for proposal in proposals:
        status_parts = [
            f"reviews: {proposal.review_count}",
            f"publications: {proposal.publication_count}",
        ]
        request = _format_optional(proposal.optimisation_request_id)
        details = "\n".join(
            [
                f"Created: {proposal.created_at.isoformat()}",
                "Optimisation request:",
                request or "not available",
                f"Articles: {proposal.selected_article_count}",
                f"Objective: {proposal.objective_value}",
                f"Publication: {proposal.publication_name or 'not available'}",
                f"Status: {', '.join(status_parts)}",
            ]
        )
        table.add_row(
            str(proposal.proposal_id),
            details,
        )
    console.print(table)


@evaluation_app.command("list")
def evaluation_list(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    evaluations = _evaluation_inspection_service(db).list(limit=limit)
    if not evaluations:
        console.print("No evaluations found.")
        return

    table = Table(title="Evaluations", show_lines=True)
    table.add_column("Evaluation ID", no_wrap=True)
    table.add_column("Details")
    for evaluation in evaluations:
        details = "\n".join(
            [
                f"Created: {evaluation.created_at.isoformat()}",
                f"Article: {evaluation.article_title or 'not available'}",
                f"Source: {evaluation.article_source or 'not available'}",
                f"Evaluator: {evaluation.evaluator}",
                f"Kind: {evaluation.kind}",
                f"Score: {_format_available(evaluation.score)}",
                f"Confidence: {_format_available(evaluation.confidence)}",
            ]
        )
        table.add_row(
            str(evaluation.evaluation_id),
            details,
        )
    console.print(table)


@evaluation_app.command("show")
def evaluation_show(
    evaluation_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _evaluation_inspection_service(db).get(evaluation_id)
    if inspection is None:
        console.print(f"Evaluation not found: {evaluation_id}")
        raise typer.Exit(1)
    _render_evaluation_inspection(inspection)


def _render_evaluation_inspection(inspection: EvaluationInspection) -> None:
    evaluation = inspection.evaluation
    summary = "\n".join(
        [
            f"[bold]Evaluation:[/bold] {evaluation.id}",
            f"[bold]Created:[/bold] {evaluation.created_at.isoformat()}",
            f"[bold]Evaluator:[/bold] {evaluation.evaluator}",
            f"[bold]Evaluator version:[/bold] {_format_available(evaluation.evaluator_version)}",
            f"[bold]Kind:[/bold] {evaluation.kind}",
            f"[bold]Score:[/bold] {_format_available(evaluation.score)}",
            f"[bold]Confidence:[/bold] {_format_available(evaluation.confidence)}",
            f"[bold]Rationale:[/bold] {_format_available(evaluation.rationale)}",
        ]
    )
    console.print(Panel(summary, title="Evaluation", expand=False))
    _render_evaluation_article(inspection)
    _render_evaluation_extractions(inspection)
    _render_evaluation_payload(inspection)
    _render_evaluation_workflow_events(inspection)


def _render_evaluation_article(inspection: EvaluationInspection) -> None:
    evaluation = inspection.evaluation
    article = inspection.article
    if article is None:
        details = "\n".join(
            [
                f"[bold]Article ID:[/bold] {evaluation.article_id}",
                "[bold]Status:[/bold] not available",
            ]
        )
        console.print(Panel(details, title="Article", expand=False))
        return

    details = "\n".join(
        [
            f"[bold]Article ID:[/bold] {article.id}",
            f"[bold]Title:[/bold] {article.title}",
            f"[bold]Source:[/bold] {_format_available(article.source)}",
            f"[bold]URL:[/bold] {_format_available(article.url)}",
            f"[bold]Published:[/bold] {_format_available(article.published_at.isoformat() if article.published_at else None)}",
        ]
    )
    console.print(Panel(details, title="Article", expand=False))


def _render_evaluation_extractions(inspection: EvaluationInspection) -> None:
    if not inspection.extractions:
        console.print(Panel("No related extractions found.", title="Extractions"))
        return

    table = Table(title="Related Extractions", show_lines=True)
    table.add_column("Created")
    table.add_column("Extractor")
    table.add_column("Kind")
    table.add_column("Payload")
    for extraction in inspection.extractions:
        table.add_row(
            extraction.created_at.isoformat(),
            extraction.extractor,
            extraction.kind,
            _format_structured_value(extraction.payload),
        )
    console.print(table)


def _render_evaluation_payload(inspection: EvaluationInspection) -> None:
    if inspection.payload_highlights:
        table = Table(title="Payload Highlights")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in inspection.payload_highlights.items():
            table.add_row(_format_label(key), _format_structured_value(value))
        console.print(table)

    if inspection.ai_provenance:
        table = Table(title="AI Provenance")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in inspection.ai_provenance.items():
            table.add_row(_format_label(key), _format_structured_value(value))
        console.print(table)

    if not inspection.evaluation.payload:
        console.print(Panel("No payload stored.", title="Payload"))
        return

    table = Table(title="Payload")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(inspection.evaluation.payload.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


def _render_evaluation_workflow_events(inspection: EvaluationInspection) -> None:
    if not inspection.workflow_events:
        console.print(Panel("No workflow events found.", title="Workflow"))
        return

    table = Table(title="Workflow")
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in inspection.workflow_events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


@extraction_app.command("list")
def extraction_list(
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    extractions = _extraction_inspection_service(db).list(limit=limit)
    if not extractions:
        console.print("No extractions found.")
        return

    table = Table(title="Extractions", show_lines=True)
    table.add_column("Extraction ID", no_wrap=True)
    table.add_column("Details", overflow="fold")
    for extraction in extractions:
        details = "\n".join(
            [
                f"Created: {extraction.created_at.isoformat()}",
                f"Article: {extraction.article_title or 'not available'}",
                f"Source: {extraction.article_source or 'not available'}",
                f"URL: {extraction.article_url or 'not available'}",
                f"Extractor: {extraction.extractor}",
                f"Version: {_format_available(extraction.extractor_version)}",
                f"Kind: {extraction.kind}",
                _format_details("Payload preview", extraction.payload_preview),
            ]
        )
        table.add_row(str(extraction.extraction_id), details)
    console.print(table)


@extraction_app.command("show")
def extraction_show(
    extraction_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _extraction_inspection_service(db).get(extraction_id)
    if inspection is None:
        console.print(f"Extraction not found: {extraction_id}")
        raise typer.Exit(1)
    _render_extraction_inspection(inspection)


def _render_extraction_inspection(inspection: ExtractionArtefactInspection) -> None:
    extraction = inspection.extraction
    details = "\n".join(
        [
            f"[bold]Extraction:[/bold] {extraction.id}",
            f"[bold]Created:[/bold] {extraction.created_at.isoformat()}",
            f"[bold]Extractor:[/bold] {extraction.extractor}",
            f"[bold]Extractor version:[/bold] {_format_available(extraction.extractor_version)}",
            f"[bold]Kind:[/bold] {extraction.kind}",
            f"[bold]Article:[/bold] {extraction.article_id}",
        ]
    )
    console.print(Panel(details, title="Extraction", expand=False))
    _render_extraction_article(inspection)
    _render_extraction_payload(inspection)
    _render_extraction_workflow_events(inspection)


def _render_extraction_article(inspection: ExtractionArtefactInspection) -> None:
    article = inspection.article
    if article is None:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"[bold]Article ID:[/bold] {inspection.extraction.article_id}",
                        "[bold]Status:[/bold] not available",
                    ]
                ),
                title="Article",
                expand=False,
            )
        )
        return

    details = "\n".join(
        [
            f"[bold]Article ID:[/bold] {article.id}",
            f"[bold]Title:[/bold] {article.title}",
            f"[bold]Source:[/bold] {_format_available(article.source)}",
            f"[bold]URL:[/bold] {_format_available(article.url)}",
        ]
    )
    console.print(Panel(details, title="Article", expand=False))


def _render_extraction_payload(inspection: ExtractionArtefactInspection) -> None:
    if inspection.payload_highlights:
        table = Table(title="Payload Highlights")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in inspection.payload_highlights.items():
            table.add_row(_format_label(key), _format_structured_value(value))
        console.print(table)

    if inspection.provenance:
        table = Table(title="Provenance")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in inspection.provenance.items():
            table.add_row(_format_label(key), _format_structured_value(value))
        console.print(table)

    if not inspection.extraction.payload:
        console.print(Panel("No payload stored.", title="Payload"))
        return

    table = Table(title="Payload")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(inspection.extraction.payload.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


def _render_extraction_workflow_events(
    inspection: ExtractionArtefactInspection,
) -> None:
    if not inspection.workflow_events:
        console.print(Panel("No workflow events found.", title="Workflow"))
        return

    table = Table(title="Workflow")
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in inspection.workflow_events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


@proposal_app.command("show")
def proposal_show(
    proposal_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _proposal_inspection_service(db).get(proposal_id)
    if inspection is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)
    _render_proposal_inspection(inspection)


def _render_proposal_inspection(inspection: ProposalInspection) -> None:
    proposal = inspection.proposal
    request_id = (
        str(inspection.optimisation_request.id)
        if inspection.optimisation_request
        else _format_optional(proposal.metadata.get("optimisation_request_id"))
    )
    summary = "\n".join(
        [
            f"[bold]Proposal:[/bold] {proposal.id}",
            f"[bold]Created:[/bold] {proposal.created_at.isoformat()}",
            f"[bold]Optimisation request:[/bold] {request_id or 'not available'}",
            f"[bold]Publication:[/bold] {inspection.publication_name or 'not available'}",
            f"[bold]Objective value:[/bold] {proposal.objective_value}",
            f"[bold]Selected articles:[/bold] {len(proposal.article_ids)}",
        ]
    )
    console.print(Panel(summary, title="Issue Proposal", expand=False))
    _render_selected_articles(inspection)
    _render_constraints(inspection)
    _render_workflow_events(inspection)
    _render_reviews(inspection)
    _render_publications(inspection)
    _render_metadata(inspection)


def _render_selected_articles(inspection: ProposalInspection) -> None:
    console.print("[bold]Selected Articles[/bold]")
    for article in inspection.selected_articles:
        reading = (
            "not available"
            if article.reading_minutes is None
            else f"{article.reading_minutes} min"
        )
        relevance = (
            "not available"
            if article.relevance_score is None
            else str(article.relevance_score)
        )
        details = "\n".join(
            [
                f"[bold]Title:[/bold] {article.title}",
                f"[bold]Source:[/bold] {article.source or 'not available'}",
                f"[bold]URL:[/bold] {article.url or 'not available'}",
                f"Reading time: {reading}",
                f"Relevance: {relevance}",
                f"Rationale: {article.relevance_rationale or 'not available'}",
            ]
        )
        console.print(Panel(details, title=str(article.article_id), expand=False))


def _render_constraints(inspection: ProposalInspection) -> None:
    if not inspection.constraint_results:
        console.print(Panel("No constraint results available.", title="Constraints"))
        return

    table = Table(title="Constraints")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Satisfied")
    table.add_column("Value")
    table.add_column("Target")
    table.add_column("Penalty")
    table.add_column("Message")
    for constraint in inspection.constraint_results:
        table.add_row(
            constraint.name,
            constraint.kind,
            str(constraint.satisfied),
            _format_optional(constraint.value),
            _format_optional(constraint.target),
            str(constraint.penalty),
            constraint.message or "",
        )
    console.print(table)


def _render_workflow_events(inspection: ProposalInspection) -> None:
    if not inspection.workflow_events:
        console.print(Panel("No workflow events found.", title="Workflow"))
        return

    table = Table(title="Workflow")
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in inspection.workflow_events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


def _render_reviews(inspection: ProposalInspection) -> None:
    if not inspection.reviews:
        console.print(Panel("No reviews found.", title="Reviews"))
        return

    table = Table(title="Reviews")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Reviewer")
    table.add_column("Decision")
    table.add_column("Comments")
    for review in inspection.reviews:
        table.add_row(
            review.created_at.isoformat(),
            str(review.id),
            review.reviewer,
            review.decision.value,
            review.comments or "",
        )
    console.print(table)


def _render_publications(inspection: ProposalInspection) -> None:
    if not inspection.publications:
        console.print(Panel("No publications found.", title="Publications"))
        return

    table = Table(title="Publications")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Title")
    table.add_column("Sections")
    for publication in inspection.publications:
        table.add_row(
            publication.created_at.isoformat(),
            str(publication.id),
            publication.title,
            str(len(publication.sections)),
        )
    console.print(table)


def _render_metadata(inspection: ProposalInspection) -> None:
    metadata = _without_metadata_keys(
        inspection.metadata,
        {
            "article_ids",
            "articles",
            "optimisation_request_id",
            "selected_article_ids",
            "selected_articles",
        },
    )
    if not metadata:
        return

    table = Table(title="Metadata")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(metadata.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


@workflow_app.command("record")
def workflow_record(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    event_type: str = typer.Option(..., "--event-type"),
    actor: str | None = typer.Option(None, "--actor"),
    reason: str | None = typer.Option(None, "--reason"),
    payload: str = typer.Option("{}", "--payload"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    event = WorkflowEvent(
        artefact_type=artefact_type,
        artefact_id=artefact_id,
        event_type=event_type,
        actor=actor,
        reason=reason,
        payload=parse_payload(payload),
    )
    SQLiteWorkflowEventRepository(db).insert(event)
    console.print(f"Recorded workflow event {event.id}")


@workflow_app.command("history")
def workflow_history(
    artefact_type: str | None = typer.Option(None, "--artefact-type"),
    artefact_id: UUID | None = typer.Option(None, "--artefact-id"),
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    events = SQLiteWorkflowEventRepository(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id, limit=limit
    )
    if not events:
        console.print("No workflow events found.")
        return

    table = Table(title="Workflow Events")
    table.add_column("Created")
    table.add_column("Artefact")
    table.add_column("Event", no_wrap=True)
    table.add_column("Actor")
    table.add_column("Reason")
    for event in events:
        table.add_row(
            event.created_at.isoformat(),
            f"{event.artefact_type}:{event.artefact_id}",
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


@workflow_app.command("state")
def workflow_state(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    events = SQLiteWorkflowEventRepository(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id
    )
    state = WorkflowProjection().state_for(events)
    console.print(f"Workflow state: {state}")


@review_app.command("create")
def review_create(
    artefact_type: str = typer.Option(..., "--artefact-type"),
    artefact_id: UUID = typer.Option(..., "--artefact-id"),
    reviewer: str = typer.Option(..., "--reviewer"),
    decision: ReviewDecision = typer.Option(..., "--decision"),
    comments: str | None = typer.Option(None, "--comments"),
    finding: list[str] | None = typer.Option(None, "--finding"),
    recommendation: list[str] | None = typer.Option(None, "--recommendation"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    review = Review(
        artefact_type=artefact_type,
        artefact_id=artefact_id,
        reviewer=reviewer,
        decision=decision,
        comments=comments,
        findings=parse_key_values(finding, "--finding"),
        recommendations=parse_key_values(recommendation, "--recommendation"),
    )
    SQLiteReviewRepository(db).insert(review)
    record_review_submitted(review, db)
    console.print(f"Created review {review.id}")


@review_app.command("list")
def review_list(
    artefact_type: str | None = typer.Option(None, "--artefact-type"),
    artefact_id: UUID | None = typer.Option(None, "--artefact-id"),
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    reviews = _review_inspection_service(db).list(
        artefact_type=artefact_type, artefact_id=artefact_id, limit=limit
    )
    if not reviews:
        console.print("No reviews found.")
        return

    table = Table(title="Reviews", show_lines=True)
    table.add_column("Review ID", no_wrap=True)
    table.add_column("Details")
    for review in reviews:
        details = "\n".join(
            [
                f"Created: {review.created_at.isoformat()}",
                f"Reviewer: {review.reviewer}",
                f"Decision: {review.decision}",
                f"Artefact type: {review.artefact_type}",
                f"Artefact ID: {review.artefact_id}",
                f"Comments: {review.comments_preview or 'not available'}",
            ]
        )
        table.add_row(str(review.review_id), details)
    console.print(table)


@review_app.command("show")
def review_show(
    review_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _review_inspection_service(db).get(review_id)
    if inspection is None:
        console.print(f"Review not found: {review_id}")
        raise typer.Exit(1)
    _render_review_inspection(inspection)


def _render_review_inspection(inspection: ReviewInspection) -> None:
    review = inspection.review
    details = "\n".join(
        [
            f"[bold]Review:[/bold] {review.id}",
            f"[bold]Created:[/bold] {review.created_at.isoformat()}",
            f"[bold]Reviewer:[/bold] {review.reviewer}",
            f"[bold]Decision:[/bold] {review.decision.value}",
            f"[bold]Comments:[/bold] {_format_available(review.comments)}",
            f"[bold]Reviewed artefact:[/bold] {review.artefact_type}:{review.artefact_id}",
        ]
    )
    console.print(Panel(details, title="Review", expand=False))
    _render_review_proposal_context(inspection)
    _render_review_publications(inspection)
    _render_review_workflow(inspection)
    _render_review_metadata(inspection)


def _render_review_proposal_context(inspection: ReviewInspection) -> None:
    review = inspection.review
    if review.artefact_type != "issue_proposal":
        console.print(
            Panel(
                "Detailed inspection for this artefact type is not currently available.",
                title="Reviewed Artefact",
            )
        )
        return

    proposal = inspection.issue_proposal
    if proposal is None:
        console.print(Panel("IssueProposal not found.", title="IssueProposal"))
        return

    request_id = (
        str(inspection.optimisation_request.id)
        if inspection.optimisation_request
        else "not available"
    )
    details = "\n".join(
        [
            f"[bold]Proposal:[/bold] {proposal.id}",
            f"[bold]Created:[/bold] {proposal.created_at.isoformat()}",
            f"[bold]Optimiser:[/bold] {proposal.optimiser}",
            f"[bold]Selected articles:[/bold] {len(proposal.article_ids)}",
            f"[bold]Objective value:[/bold] {proposal.objective_value}",
            f"[bold]Optimisation request:[/bold] {request_id}",
        ]
    )
    console.print(Panel(details, title="IssueProposal Context", expand=False))


def _render_review_publications(inspection: ReviewInspection) -> None:
    if not inspection.publications:
        console.print(Panel("No linked publications found.", title="Publications"))
        return

    table = Table(title="Linked Publications")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Title")
    for publication in inspection.publications:
        table.add_row(
            publication.created_at.isoformat(),
            str(publication.id),
            publication.title,
        )
    console.print(table)


def _render_review_workflow(inspection: ReviewInspection) -> None:
    if not inspection.review_workflow_events:
        console.print(
            Panel("No review workflow events found.", title="Review Workflow")
        )
    else:
        _render_workflow_table("Review Workflow", inspection.review_workflow_events)

    if not inspection.artefact_workflow_events:
        console.print(
            Panel(
                "No reviewed artefact workflow events found.", title="Artefact Workflow"
            )
        )
    else:
        _render_workflow_table("Artefact Workflow", inspection.artefact_workflow_events)


def _render_review_metadata(inspection: ReviewInspection) -> None:
    review = inspection.review
    if review.findings:
        _render_key_value_table("Findings", review.findings)
    if review.recommendations:
        _render_key_value_table("Recommendations", review.recommendations)
    if inspection.metadata:
        _render_key_value_table("Metadata", inspection.metadata)
    if not review.findings and not review.recommendations and not inspection.metadata:
        console.print(Panel("No metadata stored.", title="Review Metadata"))


def _render_key_value_table(title: str, values: dict[str, object]) -> None:
    table = Table(title=title)
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(values.items()):
        table.add_row(str(key), _format_structured_value(value))
    console.print(table)


@publication_app.command("create")
def publication_create(
    proposal_id: UUID = typer.Option(..., "--proposal-id"),
    title: str = typer.Option(..., "--title"),
    subtitle: str | None = typer.Option(None, "--subtitle"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    proposal = SQLiteIssueProposalRepository(db).get(proposal_id)
    if proposal is None:
        console.print(f"Issue proposal not found: {proposal_id}")
        raise typer.Exit(1)

    publication = PublicationBuilder().build(
        proposal=proposal,
        articles=SQLiteArticleRepository(db).list(),
        extractions=SQLiteExtractionRepository(db).list(),
        evaluations=SQLiteEvaluationRepository(db).list(),
        title=title,
        subtitle=subtitle,
    )
    SQLitePublicationRepository(db).insert(publication)
    record_publication_created(publication, db)
    console.print(f"Created publication {publication.id}")


@publication_app.command("list")
def publication_list(
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    publications = _publication_inspection_service(db).list(limit=limit)
    if not publications:
        console.print("No publications found.")
        return

    table = Table(title="Publications", show_lines=True)
    table.add_column("Publication ID", no_wrap=True)
    table.add_column("Details")
    for publication in publications:
        details = "\n".join(
            [
                f"Created: {publication.created_at.isoformat()}",
                f"Title: {publication.title}",
                f"Subtitle: {publication.subtitle or 'not available'}",
                f"Proposal: {publication.proposal_id}",
                f"Sections: {publication.section_count}",
                f"Articles: {publication.article_count}",
                f"Rendered outputs: {publication.rendered_output_count}",
                f"Status: {publication.status or 'not available'}",
            ]
        )
        table.add_row(str(publication.publication_id), details)
    console.print(table)


@publication_app.command("show")
def publication_show(
    publication_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    inspection = _publication_inspection_service(db).get(publication_id)
    if inspection is None:
        console.print(f"Publication not found: {publication_id}")
        raise typer.Exit(1)
    _render_publication_inspection(inspection)


def _render_publication_inspection(inspection: PublicationInspection) -> None:
    publication = inspection.publication
    request_id = (
        str(inspection.optimisation_request.id)
        if inspection.optimisation_request
        else "not available"
    )
    details = "\n".join(
        [
            f"[bold]Publication:[/bold] {publication.id}",
            f"[bold]Created:[/bold] {publication.created_at.isoformat()}",
            f"[bold]Title:[/bold] {publication.title}",
            f"[bold]Subtitle:[/bold] {_format_available(publication.subtitle)}",
            f"[bold]Issue proposal:[/bold] {publication.proposal_id}",
            f"[bold]Optimisation request:[/bold] {request_id}",
            f"[bold]Sections:[/bold] {len(publication.sections)}",
        ]
    )
    console.print(Panel(details, title="Publication", expand=False))
    _render_publication_sections(inspection)
    _render_publication_reviews(inspection)
    _render_publication_rendered_outputs(inspection)
    _render_publication_workflow(inspection)
    _render_publication_metadata(inspection)


def _render_publication_sections(inspection: PublicationInspection) -> None:
    if not inspection.sections:
        console.print(Panel("No sections found.", title="Sections"))
        return

    for section in inspection.sections:
        heading = (
            f"Section {section.order}: {section.section.heading} "
            f"({len(section.articles)} articles)"
        )
        if section.section.summary:
            console.print(Panel(section.section.summary, title=heading, expand=False))
        else:
            console.print(Panel("", title=heading, expand=False))

        for item in section.articles:
            article = item.article
            if article is None:
                details = "Article record not available."
            else:
                details = "\n".join(
                    [
                        f"Title: {article.title}",
                        f"Source: {_format_available(article.source)}",
                        f"URL: {_format_available(article.url)}",
                        f"Summary: {_format_available(article.summary)}",
                        f"Reading time: {_format_available(item.reading_minutes)}",
                        f"Relevance: {_format_available(item.relevance_score)}",
                        f"Rationale: {_format_available(item.relevance_rationale)}",
                    ]
                )
            console.print(Panel(details, title=str(item.article_id), expand=False))


def _render_publication_reviews(inspection: PublicationInspection) -> None:
    if not inspection.proposal_reviews:
        console.print(Panel("No proposal reviews found.", title="Proposal Reviews"))
        return

    table = Table(title="Proposal Reviews", show_lines=True)
    table.add_column("Review ID", no_wrap=True)
    table.add_column("Details")
    for review in inspection.proposal_reviews:
        details = "\n".join(
            [
                f"Reviewer: {review.reviewer}",
                f"Decision: {review.decision.value}",
                f"Created: {review.created_at.isoformat()}",
                f"Comments: {_format_available(review.comments)}",
            ]
        )
        table.add_row(str(review.id), details)
    console.print(table)


def _render_publication_rendered_outputs(inspection: PublicationInspection) -> None:
    if not inspection.rendered_outputs:
        console.print(
            Panel(
                "Rendered outputs are not currently recorded.",
                title="Rendered Outputs",
            )
        )
        return

    table = Table(title="Rendered Outputs", show_lines=True)
    table.add_column("Render ID", no_wrap=True)
    table.add_column("Details", overflow="fold")
    for output in inspection.rendered_outputs:
        details = "\n".join(
            [
                f"Created: {output.created_at.isoformat()}",
                f"Format: {output.format or 'not available'}",
                f"Output path: {output.output_path or 'not available'}",
            ]
        )
        table.add_row(str(output.event_id), details)
    console.print(table)


def _render_publication_workflow(inspection: PublicationInspection) -> None:
    if not inspection.publication_workflow_events:
        console.print(Panel("No publication workflow events found.", title="Workflow"))
    else:
        _render_workflow_table(
            "Publication Workflow", inspection.publication_workflow_events
        )

    if not inspection.proposal_workflow_events:
        console.print(
            Panel("No proposal workflow events found.", title="Proposal Workflow")
        )
    else:
        _render_workflow_table("Proposal Workflow", inspection.proposal_workflow_events)


def _render_workflow_table(title: str, events: list[WorkflowEvent]) -> None:
    table = Table(title=title)
    table.add_column("Created")
    table.add_column("Event")
    table.add_column("Actor")
    table.add_column("Reason")
    for event in events:
        table.add_row(
            event.created_at.isoformat(),
            event.event_type,
            event.actor or "",
            event.reason or "",
        )
    console.print(table)


def _render_publication_metadata(inspection: PublicationInspection) -> None:
    metadata = _without_metadata_keys(
        inspection.metadata,
        {
            "article_count",
            "objective_value",
            "optimiser",
            "proposal_id",
        },
    )
    if not metadata:
        console.print(Panel("No metadata stored.", title="Metadata"))
        return

    table = Table(title="Metadata")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in sorted(metadata.items()):
        table.add_row(_format_label(key), _format_structured_value(value))
    console.print(table)


@publish_app.command("markdown")
def publish_markdown(
    publication_id: UUID = typer.Option(..., "--publication-id"),
    output: Path = typer.Option(..., "--output"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    publication = SQLitePublicationRepository(db).get(publication_id)
    if publication is None:
        console.print(f"Publication not found: {publication_id}")
        raise typer.Exit(1)

    MarkdownPublisher(SQLiteArticleRepository(db).list()).publish(publication, output)
    record_publication_rendered(publication, output, db)
    console.print(f"Rendered Markdown publication {publication.id} to {output}")


@optimisation_request_app.command("create")
def optimisation_request_create(
    config: Path = typer.Option(..., "--config", "-c"),
    created_by: str | None = typer.Option(None, "--created-by"),
    parent_request_id: UUID | None = typer.Option(None, "--parent-request-id"),
    parent_proposal_id: UUID | None = typer.Option(None, "--parent-proposal-id"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = request_from_config(
        config,
        created_by=created_by,
        parent_request_id=parent_request_id,
        parent_proposal_id=parent_proposal_id,
        metadata={"source": "editorial optimisation-request create"},
    )
    SQLiteOptimisationRequestRepository(db).insert(request)
    console.print(f"Created optimisation request {request.id}")


@optimisation_request_app.command("list")
def optimisation_request_list(
    limit: int | None = typer.Option(None, "--limit"),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    requests = SQLiteOptimisationRequestRepository(db).list(limit=limit)
    if not requests:
        console.print("No optimisation requests found.")
        return

    table = Table(title="Optimisation Requests")
    table.add_column("Created")
    table.add_column("ID", no_wrap=True)
    table.add_column("Publication")
    table.add_column("Strategy")
    table.add_column("Created By")
    for request in requests:
        table.add_row(
            request.created_at.isoformat(),
            str(request.id),
            request.publication or "",
            request.strategy,
            request.created_by or "",
        )
    console.print(table)


@optimisation_request_app.command("show")
def optimisation_request_show(
    request_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = SQLiteOptimisationRequestRepository(db).get(request_id)
    if request is None:
        console.print(f"Optimisation request not found: {request_id}")
        raise typer.Exit(1)

    console.print(f"Optimisation request: {request.id}")
    console.print(f"Publication: {request.publication or ''}")
    console.print(f"Strategy: {request.strategy}")
    console.print(f"Created by: {request.created_by or ''}")
    console.print(f"Created at: {request.created_at.isoformat()}")
    _render_key_value_table("Settings", request.settings)
    _render_key_value_table("Constraints", request.constraints)
    _render_key_value_table("Goals", request.goals)
    _render_key_value_table("Preferences", request.preferences)


@optimisation_request_app.command("run")
def optimisation_request_run(
    request_id: UUID = typer.Argument(...),
    db: Path = typer.Option(Path("editorial.sqlite"), "--db"),
) -> None:
    request = SQLiteOptimisationRequestRepository(db).get(request_id)
    if request is None:
        console.print(f"Optimisation request not found: {request_id}")
        raise typer.Exit(1)

    result, _proposal = run_optimisation_request(request, db)
    console.print(f"Created issue proposal {result.proposal_id}")
    console.print(f"Selected articles: {result.selected_articles}")
    console.print(f"Objective value: {result.objective_value}")
