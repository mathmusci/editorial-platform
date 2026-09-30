# Read-only Editorial Workspace

The editorial workspace turns the platform's stored evidence and lineage into a connected
local interface. It is useful when reviewing an issue, investigating missing reading times
or evaluations, comparing proposals, and checking what reached a composed publication.

The inspection areas described here are read-only. The separate **Operations** area can run
ingestion, extraction and evaluation and therefore writes processing and evidence records.
Review submission and publication composition are available from issue pages.

## Start the workspace

Start with the file-selection screen:

```bash
editorial web
```

No configuration is loaded and no database is created until you open a workspace.
Choose existing files in the browser; other pages and actions become available once
the workspace is loaded. `--db` alone prefills the database path without opening it.

To open a configuration and database directly:

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

With `--config` but no `--db`, the existing default of `editorial.sqlite` still applies.
Starting this way can initialise that database. The workspace currently has no authentication. Keep the default loopback host rather than
exposing it on a public network.

## Change configuration and database

Choose **Change workspace** in the header (or start with `editorial web`). Use
**Choose configuration** and **Choose database** to browse files on the machine
running the server. For example, select:

```text
Configuration: examples/bis/publication-ollama-gpt-oss.yaml
Database:      bis-ollama-gpt-oss.sqlite
```

The pickers list folders first, then matching files: `.yaml` and `.yml` for
configurations; `.sqlite` only for databases. Other file extensions are hidden. Open folders
to navigate, or use **Up one folder**, **Home** and **Working directory**. Selecting
a file returns to the workspace screen without discarding the other selection.
**Cancel** leaves both selections unchanged. Displayed paths are relative to the
deployment directory (the working directory where `editorial web` was started).
The deployment directory itself appears as `.`; locations outside it use `..`.
The same relative-path display is used in the header, Configuration and operation
file details. Internal paths and stored provenance are unchanged.

Choose **Open workspace** after selecting both files. The Configuration page shows the loaded files and
settings; the header identifies the active database. All inspection pages and
subsequent operations, optimisation, reviews and composition use the selected pair.
Existing artefacts are not copied, deleted or reprocessed. Opening an older editorial
database can apply the same schema initialisation as starting the server.

The ordinary file pickers require existing files. A mistyped database name does not
create an empty database. The pickers use the
original server-side files, not browser uploads or temporary copies. They do not
preview file contents. See the [configuration editor](configuration-editor.md) to
edit publication, provider and extractor settings. Keep the server on loopback: anyone able to access this unauthenticated
UI can browse file names and select accessible local workspaces.

Switching is blocked while a processing run is queued or running in either database.
Do not run another server or CLI processing operation against those databases at the
same time. Invalid selections leave the current workspace active. Avoid changing
files on disk during a run.

The selection applies to every browser tab connected to this server, not just the
current tab. Reload old tabs before submitting actions: forms opened before a switch
are rejected. A server restart uses the original command-line paths again, or returns
to file selection if no configuration was supplied; selection
is not persisted. Opening a configuration is not evidence that it produced the
database's historical results.

### Start a fresh database

1. Choose a configuration, for example `examples/bis/publication-ollama-gpt-oss.yaml`.
2. Choose **New database**. This is enabled once a configuration is selected.
3. Keep the deployment folder (`.`), or use **Choose folder**, navigate and select
   **Use this folder**.
4. Enter a filename such as `bis-monday.sqlite` and select **Create and open database**.
5. Open **Operations** and run ingestion, extraction and evaluation, then generate
   a proposal from **Proposals**.

Creation requires a valid configuration, an existing writable folder and a `.sqlite`
filename. Existing files, including symbolic links, are never overwritten. Cancel
does not create anything. Creation opens an empty workspace: it does not copy
articles from the previous database or run providers or models automatically.
An active processing run blocks creation and switching. The selected configuration
is not copied into the database; it remains the configuration used by the workspace.

## Begin with an issue

The **Proposals** view lists every stored IssueProposal. Open one to see the complete state of
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

To resolve that diagnosis in the workspace, open **Operations**, start Extraction and
select **Missing only**. The equivalent CLI command remains:

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

When at least two proposals exist, the Proposals page provides base and candidate selectors.
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

The page describes the **active configuration**, not the full historical configuration for
every artefact. ProcessingRun records retain the configuration path and a digest of the
bytes used for each run, which proves whether two runs used the same file contents but does
not reconstruct an old file after it changes.

## Scope and operating actions

Pipeline Operations now provides durable, sequential ingestion, extraction and evaluation
runs while keeping these evidence views read-only. The
[Review and Revision workspace](review-revision-workspace.md) adds editorial decisions;
Publication editing creates linked versions in the [composition workspace](publication-composition-workspace.md). See the
[Pipeline Operations tutorial](pipeline-operations.md) for the operating workflow and the
[roadmap](../roadmap.md) for the full staged scope.
