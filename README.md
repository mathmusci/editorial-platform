# Editorial Platform

Editorial Platform is an extensible framework for evidence-based editorial decision making, combining statistical methods, deterministic algorithms, optimisation and AI within a configurable, auditable processing architecture.

Editorial Platform occupies a different design space from traditional content management systems. Rather than managing existing content, it supports the complete editorial decision-making process—from acquiring candidate material, through extraction, evaluation and optimisation, to human review and publication. See `docs/landscape.md` for a comparison with related open-source projects.

The BIS newsletter is the first reference application, not the whole platform.

The current development focus is v0.9.x Validation: proving the implemented architecture
through the BIS newsletter reference workflow, improving documentation, and recording
friction found in practical CLI use.

## Includes

- `src/editorial/` package layout
- typed domain models
- typed publication configuration loading
- provider interface with RSS and static content providers
- extractor interface with deterministic and AI-powered extractors
- evaluator interface with deterministic and AI-powered evaluators
- optimiser interface for constructing editorial issue proposals
- human review workflow for editorial approval
- publication and rendering pipeline with immutable editorial artefacts
- optimiser interface with deterministic greedy issue proposals
- immutable optimisation requests for traceable proposal generation
- generic immutable reviews for editorial judgement on any artefact
- presentation-independent Publication artefacts with Markdown rendering
- SQLite article, extraction, evaluation, issue proposal, optimisation request, review, publication, and workflow event persistence
- minimal editorial engine
- CLI commands: `editorial ingest`, `editorial extract`, `editorial evaluate`, `editorial optimise`, `editorial list`, `editorial workflow`, `editorial optimisation-request`, `editorial review`, `editorial publication`, and `editorial publish`
- tests

## Current Implementations

* Providers: RSS, Static
* Extractors: Reading Time, LLM Summary
* Evaluators: Rule-based Relevance, LLM Relevance, LLM Summary Quality
* Optimisers: Greedy
* Renderers: Markdown

## Documentation

- [Philosophy](docs/philosophy.md)
- [Architecture](docs/architecture.md)
- [Product Vision](docs/product-vision.md)
- [Roadmap](docs/roadmap.md)
- [Getting Started](docs/getting-started.md)
- [BIS Newsletter Tutorial](docs/tutorials/bis-newsletter.md)
- [Summary Model Comparison And Human Calibration](docs/tutorials/summary-model-calibration.md)

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

Configured extractors run over Articles already stored in SQLite and write separate Extraction records. The platform supports both deterministic and AI-powered extractors. Sprint 3 includes a deterministic reading-time extractor:

```yaml
extractors:
  - type: reading_time
    words_per_minute: 200
```

The extractor estimates reading time from article title, summary, and content without mutating the Article.

The first AI-powered extractor is `LLMSummaryExtractor`. It uses the provider-neutral LLM abstraction to create concise editorial summaries and stores AI provenance in the Extraction payload. Tests use the deterministic fake LLM provider; no external LLM provider is required for the core test suite.

## Evaluators

Configured evaluators run over stored Articles and their associated Extractions, then write separate Evaluation records. Evaluators are the judgement layer: they turn evidence into scores, confidence and rationale that downstream optimisers can use for article selection. Changing an extractor, such as an LLM summary model, changes stored evidence; it only changes selected articles when an evaluator uses that evidence in its scoring. The platform supports both deterministic and AI-powered evaluators. Sprint 4 includes a deterministic rule-based relevance evaluator:

```yaml
evaluators:
  - type: rule_relevance
    include: [statistics, forecasting, uncertainty]
    exclude: [football, celebrity]
    weights: {title: 5, summary: 2, content: 1}
```

Evaluation storage is idempotent by article, evaluator, and kind, so rerunning `editorial evaluate` updates existing relevance Evaluations instead of duplicating them. Use `--limit`, `--offset`, or repeatable `--article-id` options to select Articles, and `--missing-only` to resume without re-running existing article-evaluator operations.

`LLMRelevanceEvaluator` is the first AI-powered evaluator. It uses the provider-neutral LLM abstraction, expects a JSON relevance assessment from the provider, and stores AI provenance in the Evaluation payload. Tests use the deterministic fake LLM provider and do not call external APIs.

`LLMSummaryQualityEvaluator` assesses an existing summary Extraction for faithfulness, coverage, clarity and concision. It records an overall score, detailed dimensions, evidence, issues, the source Extraction and provider provenance. This judgement is separate from relevance and does not currently affect optimiser selection. It supports fake, OpenAI and Ollama providers through the same LLM abstraction.

Configured extractors and evaluators accept an optional stable `key`. This lets multiple instances of the same type store independent artefacts and resume independently with `--missing-only`, while `name` remains a human-readable display label. Existing configurations retain their type-based identity when no key is supplied, and duplicate keys are rejected before processing.

`editorial evaluation compare` compares stored summary-quality evaluator keys across a deterministic article selection. It reports aggregate and per-article dimension scores, confidence, issues, missing coverage, and separate provenance for the summary model and evaluator model without rerunning either.

Editors can record human summary-quality reference Evaluations with `editorial evaluation record-reference`, then use `editorial evaluation calibrate` to measure an LLM evaluator's mean absolute error, bias, tolerance agreement and dimension-level error. Calibration only compares judgements linked to the same stored summary Extraction.

## Optimisers

Configured optimisers run over stored Articles, Extractions, and Evaluations, then write append-only IssueProposal records. In normal workflows, Evaluations carry the editorial judgement that most directly drives optimiser selection. Sprint 5 includes a deterministic greedy optimiser:

```yaml
optimisation:
  strategy: greedy
  settings:
    max_articles: 8
    relevance_target_score: 40
    reading_time_target_minutes: 20
    mandatory_terms: [statistics, industry]
```

IssueProposal records are proposals only. They are not approved issues and carry no review or publication state. Rerunning `editorial optimise` creates a new optimisation request and a new proposal record each time.

## Optimisation Requests

OptimisationRequest records are immutable inputs to optimiser runs. They capture the
publication, strategy, settings, constraints, goals, preferences, optional creator, and
optional parent request or proposal. A proposal created from a request stores the request id
in its metadata, and a `proposal-created` WorkflowEvent is recorded for the proposal.

```bash
editorial optimisation-request create \
  --config examples/bis/publication.yaml \
  --created-by "Andy" \
  --db editorial.sqlite

editorial optimisation-request list --db editorial.sqlite
editorial optimisation-request show <request-id> --db editorial.sqlite
editorial optimisation-request run <request-id> --db editorial.sqlite
```

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

## Reviews

Review records are immutable editorial judgements about any artefact identified by
`artefact_type` and `artefact_id`. They can approve, reject, request changes, or leave a
comment. Reviews do not mutate IssueProposal records, create OptimisationRequests, trigger
optimisation, or store workflow state.

Creating a review automatically records a generic `review-submitted` WorkflowEvent against
the reviewed artefact.

```bash
editorial review create \
  --artefact-type issue_proposal \
  --artefact-id <uuid> \
  --reviewer "Andy" \
  --decision needs_changes \
  --comments "Reading time too long" \
  --finding reading_time=24 \
  --recommendation target_minutes=20

editorial review list --artefact-type issue_proposal --artefact-id <uuid>
editorial review show <review-id>
```

## Publications And Markdown Publishing

Publication records are immutable editorial artefacts created from IssueProposal records.
They are not Markdown, HTML, email, or PDF. Publisher implementations render Publications
to concrete output formats; the first implementation is a simple Markdown publisher.

Creating a Publication records `publication-created`. Rendering it to Markdown records
`publication-published`; for now this means rendered to an output artefact, not distributed
externally.

```bash
editorial publication create \
  --proposal-id <uuid> \
  --title "RSS BIS Newsletter" \
  --subtitle "Draft issue" \
  --db editorial.sqlite

editorial publication list --db editorial.sqlite
editorial publication show <publication-id> --db editorial.sqlite

editorial publish markdown \
  --publication-id <publication-id> \
  --output newsletter.md \
  --db editorial.sqlite
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
