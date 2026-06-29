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
- Optimise: optimiser plugins execute OptimisationRequest records and create IssueProposal
  records.
- Review: human reviewers create generic immutable Review records for any artefact.
- Workflow events: generic WorkflowEvent records can be attached to any artefact by
  artefact type and artefact id.

Planned capabilities:

- Publish: downstream rendering from reviewed editorial state.

AI can participate as a provider, extractor, evaluator, optimiser, reviewer assistant, or
publisher assistant. AI is not the architecture itself.

## Artefact Lineage View

Editorial artefacts are durable records produced by capabilities:

```text
Article -> Extraction -> Evaluation -> IssueProposal -> Review -> Publication
```

Important distinctions:

- Article is acquired source material.
- Extraction is structured evidence derived from an Article.
- Evaluation is a judgement about an Article using available evidence.
- IssueProposal is an optimiser output, not an approved issue.
- Review is a generic editorial judgement about any artefact.
- Publication is downstream of explicit workflow decisions.

IssueProposal records are append-only proposals. They do not contain review state, approval
state, or publication state. A proposal generated from an OptimisationRequest records the
request id in proposal metadata.

Review records are append-only and immutable. They store reviewer, decision, comments,
findings, recommendations, metadata, and the reviewed artefact identity. They do not modify
the reviewed artefact, trigger optimisation, or store workflow state.

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

WorkflowEvent is now implemented as generic infrastructure. It stores `artefact_type`,
`artefact_id`, `event_type`, optional `actor` and `reason`, a generic payload, and creation
time. It deliberately has no proposal-specific, review-specific, or publication-specific
columns.

Workflow state is not stored. The current state is projected from event history. The initial
generic projection maps events such as `proposal-created`, `review-requested`,
`review-submitted`, `proposal-approved`, `proposal-rejected`, `publication-created`, and
`publication-published` to current state labels. Unknown or missing history projects to
`unknown`.

OptimisationRequest is now implemented as the immutable input to an optimisation run. It has
no mutable status and is not itself a proposal. When a request produces an IssueProposal,
the proposal can be traced back through `metadata.optimisation_request_id`, and a
`proposal-created` WorkflowEvent is recorded for the proposal.

Review is now implemented as a generic immutable artefact. When a Review is inserted, a
`review-submitted` WorkflowEvent is recorded for the reviewed artefact with the review id
and decision in its payload. Approval rules, re-optimisation rules, AI reviewers, and
publishing remain architectural direction rather than automatic runtime behaviour.

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

- WorkflowEvent
- WorkflowState
- OptimisationRequest
- Review

Decisions are explicit editorial choices. They should be recorded as workflow events or
decision artefacts rather than implied by modifying earlier artefacts.

## Current Runtime Pipeline

The implemented v0.8 pipeline is:

```text
Discover -> Extract -> Evaluate -> Optimise -> Review -> Store
```

In concrete terms:

```text
Provider -> Article -> Extractor -> Extraction -> Evaluator -> Evaluation -> OptimisationRequest -> Optimiser -> IssueProposal -> Review
```

All outputs are stored separately. Extraction and Evaluation storage is idempotent for a
given processor and article. IssueProposal storage is append-only so repeated optimisation
runs can be compared and audited. OptimisationRequest, Review, and WorkflowEvent storage
are also append-only, providing explicit inputs, editorial judgement, and generic event
history for editorial artefacts.
