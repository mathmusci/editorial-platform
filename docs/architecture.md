# Architecture

Editorial Platform is an extensible framework for evidence-based editorial decision making.
It combines statistical methods, deterministic algorithms, optimisation, and AI within a
configurable, auditable processing architecture.

The BIS newsletter is the first reference application. It is not the whole platform.
The platform is intended to support many editorial workflows where evidence, provenance,
human judgement, and repeatable decision processes matter.

## Capability View

Capabilities are independent, configurable processing stages:

```text
Acquire -> Extract -> Evaluate -> Optimise -> Review -> Publish
```

Current implemented capabilities:

- Acquire: static and RSS providers create Article records.
- Extract: deterministic extractors create Extraction records.
- Evaluate: deterministic evaluators create Evaluation records.
- Optimise: optimiser plugins create IssueProposal records.

Planned capabilities:

- Review: human editorial review, decisions, and workflow events.
- Publish: downstream rendering from reviewed editorial state.

AI can participate as a provider, extractor, evaluator, optimiser, reviewer assistant, or
publisher assistant. AI is not the architecture itself.

## Artefact Lineage View

Editorial artefacts are durable records produced by capabilities:

```text
Article -> Extraction -> Evaluation -> IssueProposal -> Publication
```

Important distinctions:

- Article is acquired source material.
- Extraction is structured evidence derived from an Article.
- Evaluation is a judgement about an Article using available evidence.
- IssueProposal is an optimiser output, not an approved issue.
- Publication is downstream of explicit workflow decisions.

IssueProposal records are append-only proposals. They do not contain review state, approval
state, or publication state.

## Workflow View

Workflow concepts coordinate human and automated decision making:

```text
OptimisationRequest -> Optimiser -> IssueProposal -> Review(s) -> WorkflowEvent(s) -> Publication
```

The workflow layer should make editorial actions explicit:

- Re-optimisation should happen through an OptimisationRequest.
- Reviews should be recorded separately from proposals.
- Reviews should not modify IssueProposal records.
- WorkflowEvent records should describe significant transitions and decisions.
- WorkflowState should be derived from explicit events, not hidden mutation.

These concepts are architectural direction. They should not be confused with currently
implemented runtime objects unless a corresponding model exists in the codebase.

## Concepts

Artefacts are records of editorial evidence or outputs:

- Article
- Extraction
- Evaluation
- IssueProposal
- Review
- Publication

Processor capabilities produce artefacts:

- Acquire
- Extract
- Evaluate
- Optimise
- Review
- Publish

Workflow events record actions and decisions:

- OptimisationRequest
- Review
- WorkflowEvent
- WorkflowState

Decisions are explicit editorial choices. They should be recorded as workflow events or
decision artefacts rather than implied by modifying earlier artefacts.

## Current Runtime Pipeline

The implemented v0.6 pipeline is:

```text
Discover -> Extract -> Evaluate -> Optimise -> Store
```

In concrete terms:

```text
Provider -> Article -> Extractor -> Extraction -> Evaluator -> Evaluation -> Optimiser -> IssueProposal
```

All outputs are stored separately. Extraction and Evaluation storage is idempotent for a
given processor and article. IssueProposal storage is append-only so repeated optimisation
runs can be compared and audited.
