# Read-only Editorial Workspace

The editorial workspace turns the platform's stored evidence and lineage into a connected
local interface. It is useful when reviewing an issue, investigating missing reading times
or evaluations, comparing proposals, and checking what reached a composed publication.

The workspace is read-only. It does not run ingestion, extraction or evaluation, submit a
Review, change a Publication, or write to the database.

## Start the workspace

Use a configuration and database that have already been processed:

```bash
editorial web \
  --config examples/bis/publication.yaml \
  --db editorial.sqlite
```

Open `http://127.0.0.1:8000` in a browser. To use a different local port:

```bash
editorial web \
  --config examples/bis/publication.yaml \
  --db editorial.sqlite \
  --port 8010
```

The workspace currently has no authentication. Keep the default loopback host rather than
exposing it on a public network.

## Begin with an issue

The **Issues** view lists every stored IssueProposal. Open one to see the complete state of
that proposed issue:

- the derived workflow status and stored proposal state;
- selected Article count and optimiser objective;
- each workflow stage from Articles through Rendering;
- extraction and evaluation coverage for every enabled processor;
- outstanding actions derived from stored artefacts;
- selected Articles with reading time and relevance evidence;
- linked Reviews and Publications.

Coverage is calculated against the processors enabled in the supplied configuration. This
is why the workspace needs both `--config` and `--db`: SQLite supplies the stored artefacts,
while the configuration defines which extraction and evaluation operations should exist.

### Example: diagnose missing reading time

Suppose an issue contains ten Articles, and its Extraction coverage shows:

```text
Processor       Kind           Present   Missing
Reading time    reading_time         7         3
LLM summary     summary             10         0
```

The selected-Articles table identifies the three entries whose reading time is missing.
Open one of those Articles. Its Extractions section shows every stored extraction by kind
and processor. If no `reading_time` artefact appears, the problem is missing extraction
coverage, not publication rendering.

The read-only workspace stops at that diagnosis. Until Pipeline Operations is implemented,
resume the missing work through the existing CLI:

```bash
editorial extract \
  --config examples/bis/publication.yaml \
  --db editorial.sqlite \
  --missing-only \
  --progress
```

Refresh the proposal page after the command completes. Coverage is derived on every request,
so the updated artefacts appear without importing or synchronising data.

## Inspect an Article

The **Articles** view reports extraction and evaluation counts for each stored Article.
An Article page separates:

- extraction evidence, including reading time and generated summaries;
- evaluation judgement, including score, confidence and rationale;
- AI provenance such as provider, model, generator and prompt version;
- full stored payloads for less common fields;
- IssueProposals and Publications that include the Article.

This separation is intentional. An Extraction records derived evidence; an Evaluation
records a judgement using evidence. Seeing both helps explain why changing a summary model
does not necessarily change proposal selection unless an evaluator uses that summary.

## Compare proposals

When at least two proposals exist, the Issues page provides base and candidate selectors.
The comparison reports shared, added, removed and reordered Articles, objective change,
proposal-time evidence where available, and explicit evidence gaps. It reads stored
proposals and does not rerun the optimiser or recommend a winner.

## Follow editorial lineage

Use **Reviews** to inspect immutable editorial decisions and follow an IssueProposal back to
the reviewed selection. Use **Publications** to inspect ordered sections, publication-time
titles and summaries, reading time, relevance evidence and rendered outputs.

The useful path through the workspace is usually:

```text
IssueProposal -> selected Article evidence -> Review -> Publication -> rendered output
```

Each page is a view of the same artefacts used by the CLI. The browser does not maintain a
separate editorial state.

## Inspect the active configuration

Use **Configuration** to inspect what the workspace loaded at startup. The view groups
content providers, extractors, evaluators and publishers, and shows each processor's type,
stable key, enabled state and settings. It also presents editorial-policy limits,
optimisation settings, and the active configuration and database paths.

Processor names in an Issue's coverage tables link directly to their entries on this page.
This makes a coverage problem easier to interpret: the editor can move from a missing
operation count to the processor definition that establishes the expected operation.

The expandable normalized YAML is diagnostic rather than a byte-for-byte reproduction of
the source file. Comments and shorthand processor fields are normalized, and secret-like
values are redacted. Names of environment variables remain visible because they identify
configuration without revealing the values held in those variables.

The page describes the **active configuration**, not historical configuration provenance.
An artefact in the database may have been created before the file changed. A later
ProcessingRun design will need immutable configuration snapshots to make that historical
claim safely.

## Scope and next phase

The next planned UI phase is **Pipeline Operations**. It will add durable, sequential runs
for ingestion, extraction and evaluation, with article selection, missing-only resume,
force, progress, failures and status across browser refreshes. Review submission and
Publication editing follow as separate phases so every write remains explicit and
auditable. See [the roadmap](../roadmap.md) for the full staged scope.
