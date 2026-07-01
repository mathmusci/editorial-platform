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
network access. The default BIS workflow uses deterministic extractors,
evaluators and optimisers; no external AI service is required.

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
fetched, inserted and skipped duplicate articles.

### 2. Extract article evidence

Purpose: run configured extractors over the stored Articles.

```bash
editorial extract --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints article and extractor counts, then reports
how many Extractions were stored.

### 3. Evaluate relevance

Purpose: evaluate the Articles using the configured BIS relevance evaluator.

```bash
editorial evaluate --config examples/bis/publication.yaml --db bis-getting-started.sqlite
```

Expected outcome: the command prints article and evaluator counts, then reports
how many Evaluations were stored.

### 4. Optimise an issue proposal

Purpose: create an optimisation request and generate an IssueProposal.

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

List optimisation requests:

```bash
editorial optimisation-request list --db bis-getting-started.sqlite
```

Show the optimisation request printed by `editorial optimise`:

```bash
editorial optimisation-request show <request-id> --db bis-getting-started.sqlite
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

Inspect workflow events, including proposal creation, review submission,
publication creation and rendering:

```bash
editorial workflow history --db bis-getting-started.sqlite
```

List reviews:

```bash
editorial review list --db bis-getting-started.sqlite
```

List publications:

```bash
editorial publication list --db bis-getting-started.sqlite
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

Read [developer-notes.md](developer-notes.md) for observations from the first
end-to-end BIS validation run and known areas for improvement.
