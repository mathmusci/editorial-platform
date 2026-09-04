# Pipeline Operations

Pipeline Operations runs and monitors configured ingestion, extraction and evaluation from
the local editorial workspace. It is designed for long local-model workloads where an
editor needs a small test selection, visible progress and a safe way to continue after an
interruption.

## Start the workspace

Use the same configuration and database that you would pass to the processing commands:

```bash
editorial web \
  --config examples/bis/publication-ollama-qwen.yaml \
  --db bis-ollama-qwen.sqlite
```

Open `http://127.0.0.1:8000` and choose **Operations**. The workspace uses the configuration
loaded at server startup; inspect it under **Configuration** before starting an expensive
run. The workspace has no authentication, so keep it on the default loopback address.

## Run a small extraction test

The Extraction form exposes the same selection controls as the CLI:

- **Limit** processes at most that many Articles.
- **Offset** skips that many Articles before applying the limit.
- **Article IDs** restricts the selection to specific UUIDs, separated by spaces or commas.
- **Missing only** skips Article-extractor pairs whose artefacts already exist.
- **Replace existing** runs every selected operation and stores replacement artefacts.

For a ten-Article model test, set Limit to `10`, leave Offset at `0`, and select Missing
only. Articles use the same deterministic ordering as the CLI: publication date, then
creation time, then Article ID. Missing only and Replace existing are mutually exclusive.

This is equivalent to:

```bash
editorial extract \
  --config examples/bis/publication-ollama-qwen.yaml \
  --db bis-ollama-qwen.sqlite \
  --limit 10 \
  --missing-only \
  --progress
```

## Monitor a run

Starting an operation opens its run page. Extraction and evaluation report:

- completed, stored, skipped and failed operation counts;
- the current Article and processor;
- provider and model identity when the processor supplies them;
- elapsed time and an estimate of remaining time once an operation has completed;
- the exact selection options, configuration path, database path and configuration digest.

The page refreshes every two seconds while work is active. Closing the page does not cancel
the run, and reopening Operations reads its state from SQLite. Only one operation runs at a
time. Ingestion records final provider and article totals but does not yet report individual
fetch progress.

Failed Article-processor operations are counted and processing continues according to the
existing engine behavior. A failure that prevents the whole run from proceeding changes
the run status to Failed and displays a concise error without a browser stack trace.

## Resume after interruption

If the web server stops during a run, that run is marked Interrupted the next time the
workspace starts. Its completed extraction or evaluation artefacts remain in SQLite. Open
the interrupted run and choose **Resume missing work**. This creates a new run with the same
Article selection and `missing_only` enabled, so completed pairs are skipped.

Resume is deliberately a new run rather than a mutation of the old record. The original
failure or interruption remains inspectable, and WorkflowEvents record the queued, started
and terminal state of each attempt.

## Understand the boundary

Pipeline Operations is a local background runner, not a distributed job system. It remains
sequential and does not provide cancellation, concurrent workers, remote execution or user
authentication. The CLI and workspace call the same ProcessingRun service; neither shells
out to the other. Review decisions and Publication editing remain separate roadmap phases.
