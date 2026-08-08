# Roadmap

## Completed

- [x] v0.3.0 Ingestion
- [x] v0.4.0 Extraction
- [x] v0.5.0 Evaluation
- [x] v0.6.0 Optimisation & Issue Proposals
- [x] v0.7.0 Workflow Infrastructure
- [x] v0.8.0 Editorial Workflow
- [x] v0.9.0 AI Integration

## Current Phase

### v0.9.x Validation

The platform is moving from feature development into product validation. The goal of this
phase is to prove that the implemented architecture works for a real editorial workflow,
using the BIS newsletter as the reference scenario.

Objectives:

- Architecture documentation.
- BIS newsletter walkthrough.
- Real-world validation.
- CLI usability improvements.
- Documentation improvements.
- Capture observations from practical use.

The validation work has established the operational and evidence layers needed for a
credible editorial workflow:

- Accurate ingest, extraction, and evaluation reporting.
- Progress reporting and deterministic article selection.
- Selective and resumable extraction and evaluation.
- Inspection of extraction, evaluation, proposal, review, and publication artefacts.
- Deterministic explanation output and publication metadata rendering.
- Stable processor identities for running multiple extractor and evaluator instances.
- Summary-quality evaluation, model comparison, and human calibration.

The remaining v0.9.x work is to exercise these capabilities as one real BIS workflow. A
representative set of five to twenty summaries should be assessed by an editor and used to
calibrate the automated evaluator. The resulting evaluator configuration should then be used
to produce, review, and render a complete issue using only the CLI. Friction found during
that exercise should become focused usability or correctness work rather than new parallel
feature areas.

Validation success criteria:

- A complete BIS newsletter can be produced using only the CLI.
- The tutorial is complete and accurate.
- Every workflow step is documented.
- Friction points are recorded.
- Architecture documentation matches the implementation.

## Planned

Items in the versioned sections below are planned product direction. Ideas that have been
identified but have not yet been designed or agreed are listed separately under Future
candidates. Recording a candidate does not commit it to a release.

### v0.10.0 Editor Experience

The next phase moves from inspecting individual evidence artefacts to making and revising an
editorial decision. CLI application services should be implemented and validated before a
web interface is placed over them.

#### Proposal comparison and optimisation inspectability

Implemented as the first editor-experience slice:

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

Implemented as the second editor-experience slice:

- Record approval, rejection, or requested changes against a proposal.
- Create a revised OptimisationRequest from an explicit review decision.
- Generate a new proposal while preserving the reviewed proposal and its history.
- Compare the revised proposal with the original before approval.
- Make the path from request to proposal, review, revision, and approval inspectable.

#### Publication composition

Implemented as the third editor-experience slice:

- Implement manual, editor-controlled composition through the CLI before adding further
  automation or user interfaces.
- Allow an editor to control section order and article placement.
- Support editorial titles, introductions, exclusions, and other composition choices as
  explicit publication data.
- Preserve the proposal, review, and source evidence behind each publication section.
- Keep Publication separate from Markdown, HTML, email, or other rendering formats.

This work does not currently include automatic section generation, LLM-written editorial
text, additional rendering formats, or publication distribution. Those capabilities require
separate design and prioritisation.

#### Workflow overview

Implemented as the fourth editor-experience slice:

- Present the state of a complete issue in one place.
- Summarise extraction and evaluation coverage, proposals, reviews, publications, and
  outstanding actions.
- Link each status to the existing inspection and explanation commands.
- Derive state from stored artefacts and WorkflowEvents rather than hidden mutable flags.

#### Web editor

- Web UI.
- Proposal comparison and human review interface.
- Workflow visualisation.
- Publication browser.
- Publication composition controls.

The web editor should use the same application services and create the same artefacts and
WorkflowEvents as the CLI.

### v0.11.0 Production Readiness

After the editorial workflow is coherent and validated, focus on operating it reliably:

- Configuration validation, migration guidance, and safer defaults.
- Structured observability for long-running workflow operations.
- Plugin discovery and compatibility reporting.
- Deployment, backup, and recovery guidance.
- Performance work informed by measured extraction and evaluation workloads.
- End-to-end integration tests for the reference BIS workflow.
- Stable data migration and upgrade paths.

### v1.0.0 Stable Platform

Success criteria:

- Stable public interfaces.
- Complete documentation.
- Reference BIS tutorial.
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
