# Editorial Platform

Editorial Platform is an extensible framework for evidence-based editorial decision making, combining statistical methods, deterministic algorithms, optimisation and AI within a configurable, auditable processing architecture.

The BIS newsletter is the first reference application, not the whole platform.

## Includes

- `src/editorial/` package layout
- typed domain models
- typed publication configuration loading
- provider interface with static and RSS providers
- extractor interface with deterministic reading-time extraction
- evaluator interface with deterministic rule-based relevance evaluation
- optimiser interface with deterministic greedy issue proposals
- SQLite article, extraction, evaluation, issue proposal, and workflow event persistence
- minimal editorial engine
- CLI commands: `editorial ingest`, `editorial extract`, `editorial evaluate`, `editorial optimise`, `editorial list`, and `editorial workflow`
- tests

## Documentation

- [Philosophy](docs/philosophy.md)
- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Try it

```bash
editorial ingest --config examples/bis/publication.yaml --db editorial.sqlite
editorial extract --config examples/bis/publication.yaml --db editorial.sqlite
editorial evaluate --config examples/bis/publication.yaml --db editorial.sqlite
editorial optimise --config examples/bis/publication.yaml --db editorial.sqlite
editorial list --db editorial.sqlite
```

## Extractors

Configured extractors run over Articles already stored in SQLite and write separate Extraction records. Sprint 3 includes a deterministic reading-time extractor:

```yaml
extractors:
  - type: reading_time
    words_per_minute: 200
```

The extractor estimates reading time from article title, summary, and content without mutating the Article.

## Evaluators

Configured evaluators run over stored Articles and their associated Extractions, then write separate Evaluation records. Sprint 4 includes a deterministic rule-based relevance evaluator:

```yaml
evaluators:
  - type: rule_relevance
    include: [statistics, forecasting, uncertainty]
    exclude: [football, celebrity]
    weights: {title: 5, summary: 2, content: 1}
```

Evaluation storage is idempotent by article, evaluator, and kind, so rerunning `editorial evaluate` updates existing relevance Evaluations instead of duplicating them.

## Optimisers

Configured optimisers run over stored Articles, Extractions, and Evaluations, then write append-only IssueProposal records. Sprint 5 includes a deterministic greedy optimiser:

```yaml
optimisation:
  strategy: greedy
  settings:
    max_articles: 8
    relevance_target_score: 40
    reading_time_target_minutes: 20
    mandatory_terms: [statistics, industry]
```

IssueProposal records are proposals only. They are not approved issues and carry no review or publication state. Rerunning `editorial optimise` creates a new proposal record each time.

## Workflow Events

Workflow events are generic append-only records attached to any editorial artefact with
`artefact_type` and `artefact_id`. Current workflow state is derived from event history,
not stored on the artefact.

```bash
editorial workflow record \
  --artefact-type issue_proposal \
  --artefact-id <uuid> \
  --event-type review-requested \
  --actor "Andy" \
  --reason "Ready for editorial review"

editorial workflow history --artefact-type issue_proposal --artefact-id <uuid>
editorial workflow state --artefact-type issue_proposal --artefact-id <uuid>
```

## RSS Providers

Add an RSS provider to `publication.yaml` with either a feed URL or a local XML path:

```yaml
providers:
  - type: rss
    name: Industry feed
    url: "https://example.org/feed.xml"
    source: "Example Source"
```

For local fixtures or offline tests, use `path`. Relative paths are resolved from the directory containing the config file when ingested through the CLI:

```yaml
providers:
  - type: rss
    name: Fixture feed
    path: "feeds/sample.xml"
```

Articles are deduplicated by URL during ingest, so repeated RSS items or repeated runs skip URLs that are already stored.

## Test

```bash
pytest
```
