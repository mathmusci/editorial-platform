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
| Review | Human editorial response to a proposal or workflow state. |
| WorkflowEvent | Append-only record of a significant editorial action or decision attached to any artefact by `artefact_type` and `artefact_id`. |
| WorkflowState | Current state derived from workflow events, not stored directly. |
| OptimisationRequest | Immutable input to an optimiser run; explains why an IssueProposal was generated. |
| Editorial Engine | Orchestrates processing and records results. |
| Publication | Rendered artefact downstream of workflow decisions. |
