# Roadmap

## Release Baseline

Git tags are the authoritative release history. The repository progressed through the
`v0.x` releases and reached `v1.0.0`, tagged as **Explainable Editorial Platform**. Current
`main` contains post-`v1.0.0` development.

The functional areas below are deliberately not assigned release numbers. The next version
must be chosen through an explicit release decision; this roadmap does not reuse historical
version numbers or silently decide between a minor and major release.

## Completed Post-v1.0 Work

### Operational correctness and validation

Practical BIS newsletter validation established the operational and evidence layers needed
for a credible editorial workflow:

- Accurate ingest, extraction, and evaluation reporting.
- Progress reporting and deterministic article selection.
- Selective and resumable extraction and evaluation.
- Inspection of extraction, evaluation, proposal, review, and publication artefacts.
- Deterministic explanation output and publication metadata rendering.
- Stable processor identities for running multiple extractor and evaluator instances.
- Summary-quality evaluation, model comparison, and human calibration.

### Editor experience

CLI application services were implemented before introducing a web interface. They preserve
immutable artefacts, explicit decisions, and inspectable lineage.

#### Proposal comparison and optimisation inspectability

- Compare two stored IssueProposals without rerunning the optimiser.
- Show articles shared by both proposals and articles added or removed.
- Show ordering changes, reading-time totals, relevant evaluation evidence, and constraint
  outcomes.
- Distinguish differences in source evidence from differences in OptimisationRequest intent
  or optimiser settings.
- Report missing evidence that limits the comparison.
- Preserve provenance from each proposal back to its immutable OptimisationRequest.

Summary-quality evidence should influence optimisation only through an explicit,
configurable policy and only after its evaluator has been calibrated. It must not silently
replace relevance or human editorial judgement.

#### Review and revision

- Record approval, rejection, or requested changes against a proposal.
- Create a revised OptimisationRequest from an explicit review decision.
- Generate a new proposal while preserving the reviewed proposal and its history.
- Compare the revised proposal with the original before approval.
- Make the path from request to proposal, review, revision, and approval inspectable.

#### Publication composition

- Implement manual, editor-controlled composition through the CLI.
- Allow an editor to control section order and article placement.
- Support editorial titles, introductions, exclusions, and other composition choices as
  explicit publication data.
- Preserve the proposal, review, and source evidence behind each publication section.
- Keep Publication separate from Markdown, HTML, email, or other rendering formats.

This work does not include automatic section generation, LLM-written editorial text,
additional rendering formats, or publication distribution. Those capabilities require
separate design and prioritisation.

#### Workflow overview

- Present the state of a complete issue in one place.
- Summarise extraction and evaluation coverage, proposals, reviews, publications, and
  outstanding actions.
- Link each status to the existing inspection and explanation commands.
- Derive state from stored artefacts and WorkflowEvents rather than hidden mutable flags.

#### Read-only editorial workspace

- Browse IssueProposals, Articles, Reviews and Publications in a connected local interface.
- Inspect processor coverage, evidence, provenance, active configuration and artefact lineage.
- Compare stored proposals without rerunning optimisation.
- Keep every inspection view derived from the same SQLite artefacts as the CLI.

## Current Phase

### Pipeline Operations

The workspace can now run the three configured processing stages while keeping the
inspection views read-only. Web and CLI execution share one application service and create
durable ProcessingRun records in the selected SQLite database.

Current facilities:

- Start configured ingestion, extraction and evaluation from the Operations view.
- Preserve limit, offset, Article ID, missing-only and force controls.
- Execute one background run at a time, without tying work to an HTTP request.
- Persist status, counts, current Article and processor identity, elapsed time, estimated
  remaining time, errors, configuration digest and run options across browser refreshes.
- Record queued, started, completed, failed and interrupted run events.
- Resume failed or interrupted extraction and evaluation by creating a new missing-only run.
- Run CLI commands through the same ProcessingRun service and persistence model.

The current implementation is local and single-process. It does not run operations
concurrently, cancel active work, authenticate users, distribute work to another process,
or edit Reviews and Publications. A server restart marks an unfinished run interrupted;
the editor can then resume its missing work explicitly.

## Planned Functional Areas

The following areas are agreed product direction but are not assigned to a release. Scope,
acceptance criteria, and versioning must be agreed before implementation begins.

### Web editor: staged delivery

The web editor is delivered in functional phases so that every write operation has a clear
application-service boundary, durable artefact and auditable outcome.

#### 1. Read-only editorial workspace (delivered)

- Issue, Article, Review and Publication browsers.
- Issue-level workflow visualisation and processor coverage.
- Extraction and evaluation payload and provenance inspection.
- Proposal comparison and artefact lineage navigation.
- Active configuration inspection and processor links from workflow coverage.

#### 2. Pipeline Operations (current)

Run and monitor configured processing from the workspace:

- Start ingestion, extraction and evaluation using an explicit publication configuration
  and database.
- Preserve existing selection controls: limit, offset, one or more Article ids,
  missing-only and force.
- Show the current Article, processor, provider and model where available.
- Report completed, stored, skipped and failed operations, elapsed time and estimated time
  remaining.
- Keep run status durable across browser refreshes and expose failure details and safe resume
  controls.
- Keep processing sequential initially. Introduce a background `ProcessingRun` abstraction
  so request handling is separate from the long-running operation before considering
  concurrency.

Pipeline Operations calls shared application services rather than invoking CLI commands.
Its stored run records and WorkflowEvents make operator actions inspectable after the
process has finished.

#### 3. Review and revision workspace

- Submit approve, reject, needs-changes and comment decisions.
- Capture findings and recommendations as explicit Review data.
- Create linked revision requests from needs-changes reviews.
- Compare original and revised proposals before approval.
- Preserve every original artefact and WorkflowEvent.

#### 4. Publication composition workspace

- Create a Publication from an approved proposal.
- Edit publication title, subtitle, introduction and ordered sections.
- Reorder and place selected Articles, add explicit editorial summaries and record
  exclusions.
- Preview stored publication structure and invoke supported renderers.
- Preserve proposal, approval, Article and Extraction provenance.

Across every phase, the web editor must use the same application services and create the
same artefacts and WorkflowEvents as the CLI. Browser-specific state must not become a
second source of editorial truth.

### Production readiness

After the editorial workflow is coherent and validated, focus on operating it reliably:

- Configuration validation, migration guidance, and safer defaults.
- Structured observability for long-running workflow operations.
- Plugin discovery and compatibility reporting.
- Deployment, backup, and recovery guidance.
- Performance work informed by measured extraction and evaluation workloads.
- End-to-end integration tests for the reference BIS workflow.
- Stable data migration and upgrade paths.

### Ongoing platform outcomes

- Stable public interfaces.
- Complete documentation.
- Maintained reference BIS tutorial.
- Reproducible publication workflow.
- Polished editor experience.

## Future Candidates

The following areas have been identified during publication-composition discussion, but
have not been designed, prioritised, or assigned to a release. They are not current roadmap
commitments.

### AI-assisted composition

Possible capabilities include suggested section groupings and draft editorial introductions.
Before this work can be planned, the workflow must define how editors accept, edit, or reject
suggestions and how model, prompt, and source provenance is retained. Manual publication
composition is the prerequisite.

### Multi-format publication rendering

The architecture permits a Publication to be rendered as Markdown, HTML, email, PDF, or
another format. Only existing rendering behaviour is currently committed. Additional
formats, including email templates, require their own requirements and prioritisation and
must remain separate from the Publication artefact.

### Publication distribution

Sending or distributing a rendered publication is not currently planned. Any future work
would need an explicit discussion of delivery channels, recipient data, credentials,
delivery status, retries, audit history, and the boundary between Editorial Platform and
external delivery services.
