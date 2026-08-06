# Architecture

Editorial Platform is an extensible framework for evidence-based editorial decision making.
It combines statistical methods, deterministic algorithms, optimisation, and AI within a
configurable, auditable processing architecture.

The BIS newsletter is the first reference application. It is not the whole platform.
The platform is intended to support many editorial workflows where evidence, provenance,
human judgement, and repeatable decision processes matter.

## Core Concepts

Editorial Platform is built around three core concepts: artefacts, participants, and
workflows.

### Artefacts

Artefacts answer: "what do we know?"

An artefact is a durable record of editorial evidence, judgement, intent, output, or audit
history. Artefacts are stored separately and treated as immutable records, so later work can
refer back to exactly what was known or decided at a point in time.

Examples include:

- Article
- Extraction
- Evaluation
- OptimisationRequest
- IssueProposal
- Review
- Publication
- WorkflowEvent

This matters because editorial work needs traceability. A score, summary, proposal, review,
or publication should be inspectable without overwriting the source material or hiding the
decision path that produced it.

### Participants

Participants answer: "who or what performs the work?"

A participant is any human, deterministic processor, AI assistant, or renderer that
contributes to the editorial process. Participants produce artefacts, interpret artefacts,
or help move work through a workflow.

Examples include:

- RSS provider
- Static provider
- Extractor
- Evaluator
- Optimiser
- Human reviewer
- AI assistant
- Publisher or renderer

This matters because the architecture should not depend on one kind of actor. A deterministic
evaluator, an LLM-powered evaluator, and a human reviewer can all participate without making
AI, optimisation, or manual review the whole architecture.

### Workflows

Workflows answer: "how does the work progress?"

A workflow is the sequence of editorial activity that turns sources into a publication.
Workflows use participants to create artefacts and use WorkflowEvents to record important
actions and decisions.

Examples include:

- BIS newsletter workflow.
- Manual editorial workflow.
- AI-assisted workflow.

This matters because the platform must support repeatable editorial practice. Workflow
should be explicit enough to audit and reproduce, while still allowing different
publications to choose different participants and policies.

## Editorial Capabilities

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
- Publish: PublicationBuilder creates immutable Publication artefacts, and MarkdownPublisher
  renders them to Markdown files.
- Workflow events: generic WorkflowEvent records can be attached to any artefact by
  artefact type and artefact id.

Planned capabilities:

- Approval rules before publication.
- Additional rendering formats.

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
- Publication is a presentation-independent editorial artefact. It is not Markdown, HTML,
  email, or PDF.

IssueProposal records are append-only proposals. They do not contain review state, approval
state, or publication state. A proposal generated from an OptimisationRequest records the
request id in proposal metadata.

Review records are append-only and immutable. They store reviewer, decision, comments,
findings, recommendations, metadata, and the reviewed artefact identity. They do not modify
the reviewed artefact, trigger optimisation, or store workflow state.

Publication records are append-only and immutable. They store title, optional subtitle,
sections, metadata, and the proposal they were built from. Creating a Publication does not
render an output file. Publisher implementations render Publications into concrete formats;
the first implementation renders Markdown.

## Inspection And Explainability

Inspection and explainability are separate application-layer subsystems built on the stored
artefacts.

Inspection answers: "What exists?"

Inspection services load artefacts and related records so editors and developers can see
stored Articles, Evaluations, IssueProposals, Reviews, Publications and WorkflowEvents
without querying SQLite directly. Comparison services remain within the same factual
boundary; for example, summary-quality comparison aggregates stored Evaluation scores and
reports missing coverage without rerunning an evaluator.

Human quality references are Evaluation artefacts too. They record the reviewer and exact
summary Extraction alongside the same dimensions used by an automated summary-quality
evaluator. Calibration compares stored human and automated judgements only when their
summary lineage matches, preserving the distinction between measurement and generation.

Explainability answers: "What can be concluded from the recorded evidence?"

Explainability services interpret stored artefacts in editorial terms. They can summarise
proposal constraints, optimisation requests, article-selection evidence, evaluation
provenance and publication composition. They do not re-run extractors, evaluators,
optimisers or publishers. They do not call an LLM. They do not infer intent or reasoning
that was not recorded.

Common explainability concepts include:

- Evidence: stored values that support an explanation, such as extraction highlights,
  evaluation rationales, review decisions, constraint results or publication metadata.
- Provenance: recorded origin details, such as evaluator, provider, model, prompt version
  or token usage where those values exist.
- Limitations: explicit statements about missing rationale, missing provenance, missing
  evaluations, missing extractions or incomplete workflow records.
- Next actions: concrete CLI commands that let an editor inspect related artefacts.

This separation keeps inspection factual and explainability interpretive while preserving
the same audit boundary: both layers only use recorded platform artefacts.

## Editorial Workflow

The editorial lifecycle describes the human/editorial sequence of work:

```text
Sources -> Ingestion -> Articles -> Extraction -> Evaluation -> OptimisationRequest -> IssueProposal -> Review -> Publication -> Rendering
```

Each stage has a purpose, input artefacts, output artefacts, and a concrete editorial
example.

### Sources

Purpose: identify material that could be useful to a publication.

Input artefacts: none inside the platform; sources are external feeds, files, or configured
content locations.

Output artefacts: none directly. Sources are read by providers during ingestion.

Example: the RSS Business & Industrial Section newsletter uses configured RSS feeds as its
source material.

### Ingestion

Purpose: acquire source material and convert it into platform records.

Input artefacts: external source material discovered by a provider.

Output artefacts: Article records.

Example: an RSS provider reads feed items and creates Articles with title, summary, content,
source, URL, and publication time where available.

### Articles

Purpose: provide the canonical source-material artefacts for later processing.

Input artefacts: Article records created by ingestion.

Output artefacts: Articles are consumed by extractors, evaluators, and optimisers.

Example: a BIS statistical release becomes an Article that can be summarised, scored, and
considered for an issue.

### Extraction

Purpose: derive structured evidence from Articles.

Input artefacts: Article records.

Output artefacts: Extraction records.

Example: a reading-time extractor estimates how long an article will take to read. An
AI-powered summary extractor can produce a concise factual summary while recording AI
provenance.

### Evaluation

Purpose: judge Article relevance or quality using available evidence.

Input artefacts: Article and Extraction records.

Output artefacts: Evaluation records.

Example: a relevance evaluator scores whether an Article is suitable for the BIS newsletter
and records the rationale, score, confidence, and provenance.

Evaluation is the judgement layer between evidence and selection. Extractors may create
useful facts, summaries or measurements, but those Extractions do not automatically affect
article selection. They influence optimisation only when an Evaluator reads them and records
Evaluation scores or rationale that an Optimiser consumes.

### OptimisationRequest

Purpose: capture editorial intent before running an optimiser.

Input artefacts: publication configuration, editor instruction, previous proposals, or other
context.

Output artefacts: OptimisationRequest records.

Example: an editor asks for a concise issue focused on industrial statistics. The request
records strategy, settings, constraints, goals, and preferences before any proposal is
generated.

### IssueProposal

Purpose: propose a coherent selection for an issue.

Input artefacts: OptimisationRequest, Article, Extraction, and Evaluation records.

Output artefacts: IssueProposal records.

Example: a greedy optimiser selects a set of BIS Articles that meet relevance and reading
time constraints. Optimisation proposes; it does not approve or publish.

Optimisers should treat Evaluations as the primary expression of editorial judgement.
Extractions remain available as supporting evidence, but they should not be confused with
judgements unless an Evaluator has converted them into Evaluation records.

### Review

Purpose: record editorial judgement about a proposal or any other artefact.

Input artefacts: IssueProposal records, Publication records, Evaluations, Extractions, or
other artefacts under review.

Output artefacts: Review records and associated WorkflowEvents recorded by orchestration.

Example: a human reviewer marks an IssueProposal as `needs_changes` because the reading time
is too long. Reviewers decide; the proposal itself is not mutated.

### Publication

Purpose: record the editorial output that has been chosen.

Input artefacts: an IssueProposal and the editorial decisions around it.

Output artefacts: Publication records.

Example: a Publication stores the title, subtitle, sections, selected article ids, and
editorial metadata for the BIS issue. Publication records approved editorial decisions; it
is separate from Markdown, HTML, PDF, or email output.

### Rendering

Purpose: represent a Publication in a concrete delivery format.

Input artefacts: Publication records and referenced editorial artefacts.

Output artefacts: rendered files or messages outside the core Publication model.

Example: MarkdownPublisher renders a Publication to Markdown. The rendering is a
representation of the Publication, not the Publication itself.

## Workflow Events View

Editorial workflow is the conceptual sequence of editorial work. Workflow events are audit
records of what happened inside that sequence.

Workflow event concepts coordinate human and automated decision making:

```text
OptimisationRequest -> Optimiser -> IssueProposal -> Review(s) -> WorkflowEvent(s) -> Publication
```

The workflow event layer should make editorial actions explicit:

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
`proposal-created` WorkflowEvent is recorded for the proposal by application orchestration.

Review is now implemented as a generic immutable artefact. When a review is submitted
through application orchestration, a `review-submitted` WorkflowEvent is recorded for the
reviewed artefact with the review id and decision in its payload. Approval rules,
re-optimisation rules, and automatic publication selection remain architectural direction
rather than automatic runtime behaviour.

Publication is now implemented as a generic immutable artefact created from an
IssueProposal. When a Publication is created through application orchestration, a
`publication-created` WorkflowEvent is recorded for the Publication with the proposal id in
its payload. Rendering a Publication to Markdown records `publication-published` with
`format=markdown` and the output path. The event name currently means rendered to an output
artefact, not necessarily distributed externally.

## Implemented Concepts Summary

The current implementation maps the core concepts into concrete domain models and
capabilities.

Artefacts are records of editorial evidence, intent, judgement, outputs, or audit history:

- Article
- Extraction
- Evaluation
- OptimisationRequest
- IssueProposal
- Review
- Publication
- WorkflowEvent

Participants and processor capabilities produce or render artefacts:

- Acquire
- Extract
- Evaluate
- Optimise
- Review
- Publish

Workflow infrastructure records actions and decisions:

- WorkflowEvent
- WorkflowState

Decisions are explicit editorial choices. They should be recorded as workflow events or
decision artefacts rather than implied by modifying earlier artefacts.

## Current Runtime Pipeline

The current validation pipeline is:

```text
Discover -> Extract -> Evaluate -> Optimise -> Review -> Publish -> Render -> Store
```

In concrete terms:

```text
Provider -> Article -> Extractor -> Extraction -> Evaluator -> Evaluation -> OptimisationRequest -> Optimiser -> IssueProposal -> Review -> Publication -> Rendering
```

All outputs are stored separately. Extraction and Evaluation storage is idempotent for a
given processor key and article. IssueProposal storage is append-only so repeated optimisation
runs can be compared and audited. OptimisationRequest, Review, Publication, and
WorkflowEvent storage are also append-only, providing explicit inputs, editorial judgement,
presentation-independent issue structure, and generic event history for editorial
artefacts.

## Reference Implementation And BIS Validation

The RSS Business & Industrial Section newsletter is the reference implementation and
validation scenario for Editorial Platform. It is a concrete editorial workflow that
exercises the complete path from ingestion to rendering.

The BIS workflow validates both architecture and usability. Architecturally, it tests
whether Articles, Extractions, Evaluations, OptimisationRequests, IssueProposals, Reviews,
Publications, and WorkflowEvents can work together without hidden mutation or special-case
newsletter logic. From a usability perspective, it tests whether an editor can understand
and operate the workflow through the CLI.

The first BIS validation showed that the core architecture is sound. The platform can
ingest a realistic corpus, extract evidence, evaluate relevance, generate an
OptimisationRequest, produce an IssueProposal, support review, create a Publication, and
render a complete draft.

The same validation also showed where the v0.9.x phase should focus next. Inspection of
editorial artefacts needs to improve, optimisation decisions need clearer explainability,
and rendering needs more editorial presentation work. The current Markdown rendering is
useful as a representation of a Publication, but it is not yet the final measure of a
polished newsletter experience.

## Architectural Principles

### Artefacts Are Immutable

Artefacts record what was known, proposed, judged, or produced at a point in time. Later
work should create new artefacts or workflow events rather than mutating previous records.

This preserves lineage. Editors can compare proposals, revisit reviews, and understand why a
Publication was produced without losing the history that led to it.

### Workflow Is Explicit And Reproducible

Workflow should be visible in the data model. Significant editorial actions are recorded as
WorkflowEvents, and current state is projected from history rather than stored as hidden
mutable state.

Reproducibility matters because editorial decisions may need to be explained, repeated, or
challenged. A complete workflow should show what happened, in what order, and against which
artefacts.

### Participants Are Interchangeable

Providers, extractors, evaluators, optimisers, human reviewers, AI assistants, and
publishers are participants in the same architecture. The platform should allow these
participants to change without changing the meaning of the artefacts they produce.

This keeps the architecture open to deterministic rules, statistical methods, AI assistance,
manual judgement, and future integrations.

### Optimisation Proposes; Reviewers Decide

An optimiser creates an IssueProposal. It does not approve an issue, choose the final
publication, or replace editorial judgement.

Review records capture decisions and recommendations. This separation keeps optimisation
useful without allowing it to become an implicit approval mechanism.

### Human Editorial Judgement Remains Authoritative

The platform can organise evidence, surface trade-offs, and produce suggestions, but the
editorial decision remains human. Reviews and Publications make those decisions explicit.

This principle matters most when automated and AI-assisted participants are present. Their
outputs can inform judgement, but they should not silently become judgement.

### AI Augments Editorial Judgement Rather Than Replacing It

AI participants can summarise, evaluate, recommend, or draft structured requests. They are
participants in the workflow, not owners of the workflow.

AI output should be inspectable and contestable. Editors should be able to see what an AI
participant produced and decide how much weight to give it.

### Every AI Contribution Carries Provenance

AI-generated or AI-assisted artefacts should record provider, model, prompt version, and
other relevant metadata. This allows editors to understand where an output came from and how
it was produced.

Provenance is also a practical audit control. It helps distinguish deterministic processing,
human judgement, and AI assistance within the same editorial history.

### Publication Is Separate From Rendering

A Publication is the editorial artefact that records the selected issue structure and
metadata. Rendering is the representation of that Publication as Markdown, HTML, PDF, email,
or another delivery format.

Keeping these separate allows the same editorial decision to be rendered in multiple forms
without changing the underlying Publication.

### The CLI Is The Canonical Interface

The CLI is the canonical interface for validation because it exercises the application layer
directly and makes workflow steps explicit. It is also the basis for reproducible tutorials
and validation runs.

CLI usability therefore matters. The validation phase should continue improving inspection,
explainability, and workflow ergonomics through practical use.

### Future Interfaces Build On The Same Application Layer

Future web and API interfaces should use the same application concepts as the CLI. They
should create the same artefacts, record the same workflow events, and preserve the same
provenance expectations.

This avoids splitting the product into separate behaviours for different interfaces. A web
review screen, API endpoint, and CLI command should all express the same underlying editorial
workflow.
