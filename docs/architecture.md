# Architecture

The platform is a configurable editorial processing engine.

```text
Providers -> Articles -> Extractors -> Extractions -> Evaluators -> Evaluations
          -> Editorial Engine -> Decisions -> Optimisers -> Issues -> Publishers -> Publications
```

Sprint 1 implements: `Configuration -> Provider -> Article -> SQLite storage -> CLI listing`.
