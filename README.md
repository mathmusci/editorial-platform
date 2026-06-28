# Editorial Platform — Sprint 1

Sprint 1 implements a clean vertical slice of the configurable editorial processing engine.

## Includes

- `src/editorial/` package layout
- typed domain models
- typed publication configuration loading
- provider interface and static provider
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

## Test

```bash
pytest
```
