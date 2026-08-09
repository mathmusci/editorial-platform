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

## Current Phase

### Post-v1.0 product validation

The current goal is to prove the complete architecture through real editorial operation,
using the BIS newsletter as the reference scenario. A representative set of summaries
should be assessed by an editor and used to calibrate the automated evaluator. The resulting
configuration should then produce, review, compose, and render a complete issue using only
the CLI.

Friction found during this exercise should become focused usability or correctness work
rather than new parallel feature areas.

Validation success criteria:

- A complete BIS newsletter can be produced using only the CLI.
- The reference tutorial is complete and accurate.
- Every workflow step is documented.
- Friction points are recorded.
- Architecture documentation matches the implementation.

## Planned Functional Areas

The following areas are agreed product direction but are not assigned to a release. Scope,
acceptance criteria, and versioning must be agreed before implementation begins.

### Web editor

- Web UI.
- Proposal comparison and human review interface.
- Workflow visualisation.
- Publication browser.
- Publication composition controls.

The web editor should use the same application services and create the same artefacts and
WorkflowEvents as the CLI.

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
