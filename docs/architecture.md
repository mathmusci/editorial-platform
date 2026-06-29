# Architecture

The platform is a configurable editorial processing engine.

```text
Providers -> Articles -> Extractors -> Extractions -> Evaluators -> Evaluations
          -> Editorial Engine -> Decisions -> Optimisers -> Issues -> Publishers -> Publications
```

Sprint 1 implements: `Configuration -> Provider -> Article -> SQLite storage -> CLI listing`.

Sprint 3 adds: `Stored Articles -> Extractors -> Extraction records -> SQLite storage`.
Extractions are persisted separately from Articles so extractor outputs can be regenerated,
compared, and audited without mutating source Article records.

Sprint 4 adds: `Stored Articles + Extractions -> Evaluators -> Evaluation records -> SQLite storage`.
Evaluations are persisted separately from Articles and Extractions, and deterministic evaluators
receive both the Article and its associated Extractions.

Sprint 5 adds: `Stored Articles + Extractions + Evaluations -> Optimisers -> IssueProposal records -> SQLite storage`.
IssueProposal records are append-only outputs from optimiser plugins. They are not approved
issues, do not contain review state, and do not represent publication state.
