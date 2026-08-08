# Getting Started

## What is Editorial Platform?

Editorial Platform is an editorial workflow platform for ingesting, analysing,
evaluating, optimising and publishing editorial content. It is designed to make
editorial decisions explicit, reproducible and inspectable.

The BIS newsletter is the first reference workflow. This guide uses it to get
you from a fresh checkout to a rendered Markdown publication as quickly as
possible. For the architectural concepts behind the workflow, read
[architecture.md](architecture.md).

## Prerequisites

Editorial Platform supports Python 3.11 or newer.

Start from a fresh checkout of this repository and run the following commands
from the repository root.

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the package and development dependencies:

```bash
pip install -e ".[dev]"
```

The BIS example reads configured RSS feeds, so the full ingestion run requires
network access. The default BIS workflow uses deterministic extraction and
evaluation paths, plus a fake LLM summary provider for offline validation; no
external AI service is required.

## Verify the installation

Run the test suite:

```bash
pytest
```

Success means pytest completes without failures. You should see a summary ending
with all tests passing.

## Your first publication

This workflow uses `examples/bis/publication.yaml` and writes to a fresh SQLite
database named `bis-getting-started.sqlite`.

Start from a clean database:

```bash
rm -f bis-getting-started.sqlite
```

### 1. Ingest articles

Purpose: fetch the configured BIS source material and store it as Articles.

```bash
editorial ingest --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints the publication name plus counts for
fetched, added, duplicate source and already-stored articles.
The added and already-stored counts come from the repository's atomic insert
outcome, so they describe what the database accepted rather than the result of
a separate pre-insert existence check.

### 2. Extract article evidence

Purpose: run configured extractors over the stored Articles.

```bash
editorial extract --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints article and extractor counts, then reports
how many Extractions were stored. In an interactive terminal, extraction also
shows live progress for each article-extractor operation. For example, 20
articles and 2 enabled extractors means 40 operations. The progress display
shows the current article, extractor, provider and model when available,
completed operations, stored/failed counts, elapsed time and estimated
remaining time.

Progress is automatic for interactive terminals and disabled for redirected
output and CI-style non-interactive runs. To force either mode, use:

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --progress
```

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --no-progress
```

When progress is disabled, output remains concise and line-oriented for scripts
and logs.

For faster local development runs, restrict extraction to a deterministic slice
of articles. Articles are ordered by `published_at` descending, then
`created_at` descending, then `id` ascending before `--offset` and `--limit` are
applied:

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --limit 10 \
  --no-progress
```

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --offset 20 \
  --limit 10
```

To extract one known article, pass its UUID. Repeat `--article-id` to select
more than one article:

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --article-id <article-id>
```

To resume an interrupted run, use `--missing-only`. Existing article-extractor
operations are skipped and counted in the final summary:

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --missing-only \
  --progress
```

Use `--force` to explicitly re-run and replace existing extractions. `--force`
and `--missing-only` cannot be used together.

The example configuration includes both reading-time extraction and an
offline-safe fake LLM summary provider:

```yaml
extractors:
  - type: reading_time
    name: Reading time
    words_per_minute: 200
  - type: llm_summary
    name: LLM summary
    provider:
      type: fake
      response_text: "Configured validation summary."
      model: fake-summary-model
```

The fake provider is deterministic and is the best choice for local validation,
tests and demos that should not call an external service.

To use OpenAI for summaries, install the optional dependency, set the configured
environment variable, and switch the summary provider block:

```bash
pip install -e ".[openai]"
export OPENAI_API_KEY=...
```

```yaml
extractors:
  - type: llm_summary
    name: LLM summary
    provider:
      type: openai
      model: gpt-4.1-mini
      api_key_env: OPENAI_API_KEY
      temperature: 0
      max_tokens: 180
```

API keys are read from the named environment variable, not from YAML.

To use Ollama locally, install Ollama separately, start the server and pull a
model:

```bash
ollama serve
ollama pull llama3.2
```

Then configure the summary provider with `type: ollama`. Ollama uses its native
local HTTP API and does not require an API key:

```yaml
extractors:
  - type: llm_summary
    name: Local summary
    provider:
      type: ollama
      model: llama3.2
```

The default Ollama URL is `http://localhost:11434`. You can override it and pass
generation options when needed:

```yaml
extractors:
  - type: llm_summary
    name: Local summary
    provider:
      type: ollama
      model: qwen3:8b
      base_url: http://localhost:11434
      temperature: 0
      max_tokens: 200
```

### 3. Evaluate relevance

Purpose: evaluate the Articles using the configured BIS relevance evaluator.
Evaluators are the step that turns Articles and Extractions into editorial
judgements such as relevance scores, confidence and rationale. The optimiser
uses Evaluation records when selecting articles for an IssueProposal.

This distinction matters when comparing LLM summary models: changing the
`llm_summary` extractor changes the stored summary evidence, but it will not
change suggested articles unless the configured evaluator uses that evidence in
its scoring. The BIS example uses `rule_relevance`, which scores the Article
title, original summary and content with deterministic keyword rules.

```bash
editorial evaluate --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints article and evaluator counts, then reports
operation, stored, skipped and failed totals.

Evaluation uses the same deterministic Article ordering as extraction:
`published_at DESC`, then `created_at DESC`, then Article ID ascending. Use
`--limit` and `--offset` for small or paged runs, or repeat `--article-id` to
evaluate known Articles:

```bash
editorial evaluate \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --limit 10 \
  --progress
```

To resume an interrupted run, add `--missing-only`. Existing
article-evaluator operations are skipped and included in the reported totals:

```bash
editorial evaluate \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --missing-only \
  --progress
```

Use `--force` to explicitly re-run and replace existing evaluations. Normal
runs continue to refresh evaluations for backward compatibility. `--force` and
`--missing-only` cannot be used together. Evaluation remains sequential.

Relevance evaluation asks whether an article belongs in the publication.
Summary-quality evaluation asks whether a generated summary is trustworthy and
useful. Configure `llm_summary_quality` to assess an existing summary Extraction
for faithfulness, coverage, clarity and concision:

```yaml
evaluators:
  - type: llm_summary_quality
    name: Summary quality
    summary_extractor: llm_summary
    provider:
      type: fake
      model: fake-summary-quality-model
      response_text: >-
        {"faithfulness": 90, "coverage": 80, "clarity": 85,
        "concision": 75, "confidence": 0.9,
        "rationale": "The summary is accurate and clear.",
        "evidence": ["The central claim is supported by the article."],
        "issues": ["One supporting detail is omitted."]}
```

The fake provider is useful for deterministic workflow validation. For local
model evaluation, use Ollama through the same provider-neutral evaluator:

```yaml
evaluators:
  - type: llm_summary_quality
    name: Local summary quality
    summary_extractor: llm_summary
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300
```

The evaluator stores an overall score, the four dimension scores, confidence,
rationale, evidence, issues and LLM provenance. It also records the ID and
extractor name of the summary it assessed. If that configured summary
Extraction is absent or malformed, evaluation fails clearly and does not store
an Evaluation for that operation. The evaluator works with `--limit`,
`--article-id` and `--missing-only` like every other evaluator.

Summary-quality scores are inspectable but do not currently affect optimiser
selection. The optimiser continues to select articles from relevance
Evaluations; summary quality is a separate judgement about downstream summary
evidence.

To run multiple instances of the same extractor or evaluator in one database,
give each one a stable `key`. The key is the machine-readable identity stored on
its artefacts and used by `--missing-only`; `name` remains the human-readable
label shown in progress and inspection output. Keys must contain only letters,
numbers, underscores and hyphens, and must start with a letter or number.

For example, two summary models and their quality evaluations can coexist in a
single workflow:

```yaml
extractors:
  - type: llm_summary
    key: summary_qwen
    name: Qwen summary
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 200

  - type: llm_summary
    key: summary_llama
    name: Llama summary
    provider:
      type: ollama
      model: llama3.2
      temperature: 0
      max_tokens: 200

evaluators:
  - type: llm_summary_quality
    key: quality_qwen
    name: Qwen summary quality
    summary_extractor: summary_qwen
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300

  - type: llm_summary_quality
    key: quality_llama
    name: Llama summary quality
    summary_extractor: summary_llama
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300
```

Using one fixed evaluator model, as above, makes the model comparison easier to
interpret. When `key` is omitted, the existing type identity such as
`llm_summary` or `llm_summary_quality` is retained for backward compatibility.
Configuring the same type more than once without distinct keys fails before any
articles are processed.

After evaluating the summaries, compare every stored summary-quality evaluator:

```bash
editorial evaluation compare --db bis-getting-started.sqlite
```

The comparison reports evaluation coverage, average overall and dimension
scores, confidence, issue counts and provenance for each evaluator. It then
shows the same results per article, including explicit `missing` entries. The
provenance distinguishes the model that generated the summary from the model
that evaluated it.

Use repeatable `--evaluator` options to compare particular configured keys, and
the standard deterministic article selection controls for smaller experiments:

```bash
editorial evaluation compare \
  --db bis-getting-started.sqlite \
  --evaluator quality_qwen \
  --evaluator quality_llama \
  --limit 10
```

`--offset` and repeatable `--article-id` are also supported. At least two
summary-quality evaluator keys are required. Comparison reads stored artefacts
only; it does not call an LLM or change any Evaluation.

### Calibrate an LLM evaluator against human judgement

Use a small, representative set of articles to check whether an LLM
summary-quality evaluator agrees with an editor. Five to twenty varied examples
are usually enough for an initial calibration pass; they should include strong,
weak and borderline summaries rather than only obvious successes.

First inspect an article and its summary Extractions:

```bash
editorial article show <article-id> --db bis-getting-started.sqlite
editorial extraction show <summary-extraction-id> --db bis-getting-started.sqlite
```

Record the editor's assessment of that exact summary:

```bash
editorial evaluation record-reference <article-id> \
  --summary-extraction-id <summary-extraction-id> \
  --evaluator human_qwen \
  --reviewer "Editor name" \
  --faithfulness 90 \
  --coverage 80 \
  --clarity 85 \
  --concision 75 \
  --confidence 0.9 \
  --rationale "Accurate and clear, with one supporting detail omitted." \
  --evidence "The central claim is supported by the source." \
  --issue "One supporting detail is omitted." \
  --db bis-getting-started.sqlite
```

The command stores a normal `summary_quality` Evaluation with
`generated_by: human`, the reviewer, all four dimensions, rationale, evidence,
issues and the exact summary Extraction ID. Repeating the command for the same
article and evaluator key updates that reference. `--evaluator` is required; use
a distinct human evaluator key for each summary model, such as `human_qwen` and
`human_llama`.

After recording the reference set, calibrate the corresponding LLM evaluator:

```bash
editorial evaluation calibrate \
  --reference human_qwen \
  --evaluator quality_qwen \
  --tolerance 10 \
  --db bis-getting-started.sqlite
```

Calibration reports mean absolute error, signed mean error (bias), the share of
overall scores within the chosen tolerance, and mean absolute error for each
quality dimension. It also reports missing candidate evaluations, evaluations
of a different summary, and legacy evaluations whose summary lineage cannot be
verified. Only candidate and human Evaluations linked to the same summary
Extraction contribute to agreement metrics.
Signed error is calculated as candidate score minus human score, so a positive
value means the automated evaluator scores more generously than the editor.

`--limit`, `--offset` and repeatable `--article-id` options select a smaller
reference subset in deterministic article order. Calibration reads stored
artefacts only and does not invoke an LLM.

For a complete three-model example, guidance on choosing the reference set and
detailed metric interpretation, read
[Summary Model Comparison And Human Calibration](tutorials/summary-model-calibration.md).

### 4. Optimise an issue proposal

Purpose: create an optimisation request and generate an IssueProposal.
Optimisation is downstream of evaluation: it ranks and selects from Article
records using the stored Extractions and, especially, the stored Evaluations.

```bash
editorial optimise --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints the optimiser name, optimisation request
ID, selected article count, objective value and constraint results.

List the proposals created so far:

```bash
editorial proposal list --db bis-getting-started.sqlite
```

Use the proposal ID from that list to inspect what the reviewer is being asked
to approve:

```bash
editorial proposal show <proposal-id> --db bis-getting-started.sqlite
```

Use that `<proposal-id>` in the next commands.

When a later optimisation run produces another proposal, compare it with the
current proposal before review:

```bash
editorial proposal compare \
  <base-proposal-id> \
  <candidate-proposal-id> \
  --db bis-getting-started.sqlite
```

The report shows added, removed, shared, and reordered articles; proposal-time
relevance and reading-time evidence; optimisation request changes; constraint
outcomes; provenance; and missing evidence. It reads stored artefacts only and
does not rerun the optimiser or recommend a winner. For a complete revision
example, read [Comparing Issue Proposals](tutorials/proposal-comparison.md).

### 5. Review the proposal

Purpose: record editorial approval of the generated IssueProposal.

```bash
editorial review create \
  --artefact-type issue_proposal \
  --artefact-id <proposal-id> \
  --reviewer "Getting Started" \
  --decision approve \
  --comments "Approved for first publication render" \
  --db bis-getting-started.sqlite
```

Expected outcome: the command prints the new review ID and records a
`review-submitted` workflow event.

If the decision is `needs_changes`, create a linked revision request instead of
continuing to publication:

```bash
editorial review revise <review-id> \
  --config examples/bis/publication.yaml \
  --setting reading_time_target_minutes=18 \
  --run \
  --db bis-getting-started.sqlite
```

The original proposal and Review remain unchanged. The command records their
lineage on a new OptimisationRequest, optionally creates a candidate proposal,
and prints the corresponding `editorial proposal compare` command. Review
recommendations are retained as evidence but become optimiser overrides only
when the editor supplies them explicitly. See
[Review And Revision](tutorials/review-and-revision.md) for the complete loop.

### 6. Create a Publication

Purpose: turn the approved proposal into a presentation-independent Publication
record.

```bash
editorial publication create \
  --proposal-id <proposal-id> \
  --title "RSS BIS Newsletter" \
  --subtitle "Getting started draft" \
  --db bis-getting-started.sqlite
```

Expected outcome: the command prints `Created publication <publication-id>`.
Use that `<publication-id>` when rendering.

### 7. Render Markdown

Purpose: render the Publication to a Markdown file.

```bash
editorial publish markdown \
  --publication-id <publication-id> \
  --output bis-newsletter.md \
  --db bis-getting-started.sqlite
```

Expected outcome: the command prints that the Markdown publication was rendered
to `bis-newsletter.md`. Open that file to inspect the generated newsletter.

## Inspecting the workflow

Use these commands to inspect what the previous workflow produced.

List and inspect Article artefacts:

```bash
editorial article list --db bis-getting-started.sqlite
editorial article show <article-id> --db bis-getting-started.sqlite
```

List and inspect Extraction artefacts:

```bash
editorial extraction coverage \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite
editorial extraction list --db bis-getting-started.sqlite
editorial extraction show <extraction-id> --db bis-getting-started.sqlite
```

The coverage command compares every selected article with the enabled
extractors in the configuration. It reports overall and per-extractor present
and missing counts, then shows each article's extraction IDs, payload
highlights and provenance. To diagnose missing reading-time evidence without
listing complete articles, run:

```bash
editorial extraction coverage \
  --config examples/bis/publication.yaml \
  --db bis-getting-started.sqlite \
  --extractor reading_time \
  --missing-only
```

Coverage uses the same deterministic article ordering as extraction. Use
`--limit`, `--offset` or repeatable `--article-id` options to inspect a smaller
subset.

List optimisation requests:

```bash
editorial optimisation-request list --db bis-getting-started.sqlite
```

Show the optimisation request printed by `editorial optimise`:

```bash
editorial optimisation-request show <request-id> --db bis-getting-started.sqlite
```

Explain what that optimisation request asked the optimiser to balance and what
linked proposal it produced:

```bash
editorial explain optimisation-request <request-id> --db bis-getting-started.sqlite
```

List and inspect Evaluation artefacts:

```bash
editorial evaluation list --db bis-getting-started.sqlite
editorial evaluation show <evaluation-id> --db bis-getting-started.sqlite
```

List and inspect IssueProposal artefacts:

```bash
editorial proposal list --db bis-getting-started.sqlite
editorial proposal show <proposal-id> --db bis-getting-started.sqlite
```

Explain why an IssueProposal looks the way it does:

```bash
editorial explain proposal <proposal-id> --db bis-getting-started.sqlite
```

All `editorial explain` commands use the same editorial section vocabulary
where the recorded information is available: Summary, What Happened, Why It
Happened, Evidence, Constraints and Trade-offs, Limitations, Related Artefacts
and Next Actions. The wording is deterministic and based only on stored
artefacts; it does not recreate missing reasoning or infer editorial intent.

The same explanation format is available for a particular article selection,
evaluation or publication:

```bash
editorial explain article-selection \
  <proposal-id> <article-id> \
  --db bis-getting-started.sqlite
editorial explain evaluation <evaluation-id> --db bis-getting-started.sqlite
editorial explain publication <publication-id> --db bis-getting-started.sqlite
```

Inspection commands render stored metadata as labelled fields rather than raw
JSON. Provider, model, prompt version and related generation fields appear in a
separate Provenance section. Metadata already shown as part of an artefact's
identity or structure is not repeated, while additional metadata remains
visible. `publication show` also includes metadata stored on individual
publication sections.

Inspect workflow events, including proposal creation, review submission,
publication creation and rendering:

```bash
editorial workflow history --db bis-getting-started.sqlite
```

List and inspect Review artefacts:

```bash
editorial review list --db bis-getting-started.sqlite
editorial review show <review-id> --db bis-getting-started.sqlite
```

List and inspect Publication artefacts:

```bash
editorial publication list --db bis-getting-started.sqlite
editorial publication show <publication-id> --db bis-getting-started.sqlite
```

These commands are enough to confirm that the first workflow completed. They are
not the full CLI reference.

## What happened?

The BIS sources were ingested into Article records. Extractions were created
from those Articles, then Evaluations scored their relevance to the BIS
newsletter.

The optimiser created an OptimisationRequest and generated an IssueProposal. A
reviewer approved that proposal. A Publication was created from it, and the
Publication was rendered to Markdown.

The important model is: optimisation proposes, reviewers decide, publications
record the chosen editorial output, and publishers render that output into a
concrete format.

## Next steps

Read [architecture.md](architecture.md) for the domain model, artefact lifecycle
and workflow concepts.

Read [tutorials/bis-newsletter.md](tutorials/bis-newsletter.md) for the BIS
newsletter validation walkthrough and editorial context.

Read [tutorials/proposal-comparison.md](tutorials/proposal-comparison.md) to
compare optimisation runs and understand article, request, constraint, and
evidence changes before review.

Read [tutorials/review-and-revision.md](tutorials/review-and-revision.md) to
turn requested changes into a linked request and candidate proposal without
overwriting the original editorial history.

Read [developer-notes.md](developer-notes.md) for observations from the first
end-to-end BIS validation run and known areas for improvement.
