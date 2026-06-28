# Editorial Platform

A configurable editorial processing engine.

## Includes

- `src/editorial/` package layout
- typed domain models
- typed publication configuration loading
- provider interface with static and RSS providers
- SQLite article persistence
- minimal editorial engine
- CLI commands: `editorial ingest` and `editorial list`
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
editorial list --db editorial.sqlite
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
