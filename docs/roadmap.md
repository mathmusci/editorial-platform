# Roadmap

## Completed

### v0.3 Ingestion

Completed:

- Configurable publication loading.
- Provider interface.
- Static and RSS providers.
- SQLite Article persistence.
- `editorial ingest`.

### v0.4 Extraction

Completed:

- Extraction domain persistence.
- Extractor factory.
- Deterministic reading-time extractor.
- `editorial extract`.

### v0.5 Evaluation

Completed:

- Evaluation domain persistence.
- Evaluator factory.
- Deterministic rule-based relevance evaluator.
- Evaluators receive Articles and associated Extractions.
- `editorial evaluate`.

### v0.6 Optimisation And Issue Proposals

Completed:

- IssueProposal and ConstraintResult domain models.
- Optimiser factory.
- Deterministic greedy optimiser.
- Append-only IssueProposal persistence.
- `editorial optimise`.

## Planned

### v0.7 Editorial Workflow

Planned:

- OptimisationRequest.
- Review records.
- WorkflowEvent records.
- WorkflowState derived from explicit events.
- Review of IssueProposal records without mutating proposals.

### v0.8 Publishing

Planned:

- Publication capability.
- Publisher plugins.
- Rendering from reviewed workflow state.
- Publication artefact persistence.

### v0.9 Agents And AI Providers

Planned:

- AI-assisted providers and processors.
- Agent participation in acquisition, extraction, evaluation, optimisation, review support,
  and publication support.
- Provenance and audit controls for AI outputs.

### v1.0 Stable Platform

Planned:

- Stable configuration contracts.
- Stable processor interfaces.
- End-to-end auditable editorial workflow.
- Reference applications beyond the BIS newsletter.
