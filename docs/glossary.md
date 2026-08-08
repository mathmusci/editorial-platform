# Glossary

| Term | Meaning |
|---|---|
| Provider | Retrieves or discovers content and emits Articles. |
| Article | Canonical representation of discovered content. |
| Extractor | Derives structured knowledge from an Article. |
| Extraction | Immutable structured evidence derived from an Article. |
| Evaluator | Produces a judgement from an Article and its Extractions. |
| Evaluation | Immutable judgement from an Evaluator. |
| Optimiser | Produces IssueProposal records from Articles, Extractions, and Evaluations. |
| IssueProposal | Append-only optimiser output; not an approved issue. |
| Review | Immutable editorial judgement about any artefact, with decision, comments, findings, and recommendations. |
| PublicationArticle | Publication-time snapshot of an included Article's editorial title, summary, source, and URL, with source Article and optional summary Extraction provenance. |
| PublicationSection | Ordered, presentation-independent group of PublicationArticles with a heading, optional introduction, and editorial metadata. |
| PublicationExclusion | Explicit record that a proposed Article was omitted from a Publication, including the editorial reason. |
| Publication composition | Manual process of arranging every proposed Article into a Publication section or an explicit exclusion after proposal approval. |
| WorkflowEvent | Append-only record of a significant editorial action or decision attached to any artefact by `artefact_type` and `artefact_id`. |
| WorkflowState | Current state derived from workflow events, not stored directly. |
| Workflow overview | Proposal-anchored, inspection-only summary of evidence coverage, editorial stages, linked artefacts, and outstanding actions. |
| OptimisationRequest | Immutable input to an optimiser run; explains why an IssueProposal was generated. |
| Editorial Engine | Orchestrates processing and records results. |
| Publication | Immutable presentation-independent editorial artefact composed from an approved IssueProposal and reproducible content snapshots. |
| Publisher | Renders a Publication into a concrete output format. |
| MarkdownPublisher | Simple Publisher that writes a Publication to a Markdown file. |
