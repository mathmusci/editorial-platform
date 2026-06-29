# Editorial Platform

A configurable editorial processing engine.

## Includes

- `src/editorial/` package layout
- typed domain models
- typed publication configuration loading
- provider interface with static and RSS providers
- extractor interface with deterministic reading-time extraction
- SQLite article and extraction persistence
- minimal editorial engine
- CLI commands: `editorial ingest`, `editorial extract`, and `editorial list`
- tests

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
