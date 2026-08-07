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

- Record approval, rejection, or requested changes against a proposal.
- Create a revised OptimisationRequest from an explicit review decision.
- Generate a new proposal while preserving the reviewed proposal and its history.
- Compare the revised proposal with the original before approval.
- Make the path from request to proposal, review, revision, and approval inspectable.

#### Publication composition

- Allow an editor to control section order and article placement.
- Support editorial titles, introductions, exclusions, and other composition choices as
  explicit publication data.
- Preserve the proposal, review, and source evidence behind each publication section.
- Keep Publication separate from Markdown, HTML, email, or other rendering formats.

#### Workflow overview

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
