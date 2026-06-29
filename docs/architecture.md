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
