# Roadmap

## Completed

### v0.3.0 Ingestion

Completed:

- Configurable publication loading.
- Provider interface.
- Static and RSS providers.
- SQLite Article persistence.
- `editorial ingest`.

### v0.4.0 Extraction

Completed:

- Extraction domain persistence.
- Extractor factory.
- Deterministic reading-time extractor.
- `editorial extract`.

### v0.5.0 Evaluation

Completed:

- Evaluation domain persistence.
- Evaluator factory.
- Deterministic rule-based relevance evaluator.
- Evaluators receive Articles and associated Extractions.
- `editorial evaluate`.

### v0.6.0 Optimisation & Issue Proposals

Completed:

- IssueProposal and ConstraintResult domain models.
- Optimiser factory.
- Deterministic greedy optimiser.
- Append-only IssueProposal persistence.
- Immutable OptimisationRequest records.
- Request-aware optimiser execution.
- Proposal traceability through `metadata.optimisation_request_id`.
- `editorial optimise`.
- `editorial optimisation-request create`, `list`, `show`, and `run`.

### v0.7.0 Workflow Infrastructure

Completed:

- Generic WorkflowEvent domain model.
- Append-only SQLite WorkflowEvent persistence.
- Workflow state projection from event history.
- Automatic `proposal-created` WorkflowEvent recording when a request creates a proposal.
- `editorial workflow record`, `editorial workflow history`, and `editorial workflow state`.

### v0.8.0 Editorial Workflow

Completed:

- Immutable Review domain model with approve, reject, needs_changes, and comment decisions.
- Append-only SQLite Review persistence.
- Reviews attached by generic `artefact_type` and `artefact_id`.
- Findings and recommendations persistence.
- Workflow recording for submitted reviews.
- Immutable Publication and PublicationSection domain models.
- Append-only SQLite Publication persistence.
- PublicationBuilder for creating Publication artefacts from IssueProposal records.
- Publisher protocol and MarkdownPublisher.
- Workflow recording for Publication creation and Markdown rendering.
- Repository decoupling so repositories persist only their own artefacts.
- SQLite repository helper cleanup.
- Model and CLI organisation cleanup.
- `editorial review create`, `list`, and `show`.
- `editorial publication create`, `list`, and `show`.
- `editorial publish markdown`.

## Planned

### v0.9.0 AI Integration

Planned:

- Provider-neutral LLM prompt, message, response, and provider abstractions.
- Deterministic fake LLM provider for tests and future AI participant development.
- AI-assisted providers and processors.
- LLM review assistant that can produce Review recommendations without changing workflow rules.
- AI participants in acquisition, extraction, evaluation, optimisation, review support, and publication support.
- Explicit provenance and audit controls for AI-generated or AI-assisted outputs.
- Configuration patterns for enabling AI participants without making AI the platform architecture.
- No automatic replacement of human workflow decisions.

### v1.0.0 Stable Platform

Planned:

- Stable configuration contracts.
- Stable processor interfaces.
- End-to-end auditable editorial workflow.
- Reference applications beyond the BIS newsletter.
