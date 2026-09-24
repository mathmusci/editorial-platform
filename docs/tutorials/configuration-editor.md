# Configuration Editor

The editor covers publication details, content providers, extractors, evaluators,
editorial policy, optimisation and publishers.
Start with `editorial web`, then choose **New configuration**, or select an existing
YAML file and choose **Edit selected configuration**. In an open workspace, choose
**Configuration > Edit configuration**.

The main configuration areas are separated into collapsible sections. They start
open, can be collapsed from their headers, and can be reached directly from the
section links at the top of the form. Processor counts in the headers make larger
configurations easier to scan.

## Create a Small Extraction Trial

1. Enter a publication name and description.
2. Under Content providers, choose **RSS feed** and **Add provider**. Enter a feed
   URL or a local feed path and an optional source name.
3. Under Extractors, choose **Reading time** and **Add extractor**. Set words per
   minute, for example 200.
4. Add an **LLM summary** extractor. Choose `ollama`, then **Update provider
   fields**. Choose `qwen3.5:9b`, `deepseek-r1:8b` or `gpt-oss:20b`, then enter an
   optional base URL, temperature and maximum tokens. OpenAI currently offers
   `gpt-4.1-mini`.
5. Enter a filename such as `local-trial.yaml` and choose **Save**.
6. Choose **Use configuration**, select or create a database, and **Open
   workspace**. In Operations, run ingestion and then extraction.

## Configure Editorial Evaluation

Under **Evaluators**, choose the judgement the workflow should create:

- **Rule relevance** scores configured include and exclude terms wherever they
  occur in an article's title, summary or content. Enter one term per line. The
  weights control the relative importance of matches in those three fields.
- **LLM relevance** asks a fake, OpenAI or Ollama provider to judge whether the
  article satisfies the configured criterion. Its relevance Evaluation can be
  consumed by optimisation.
- **LLM summary quality** judges the output of a configured LLM summary extractor.
  Select that extractor by its stable key. Summary-quality evidence is available
  for inspection and calibration but does not currently alter optimisation.

Give multiple evaluators of the same type distinct processor keys. Those keys are
stored on Evaluations and determine whether `--missing-only` considers an
article-evaluator operation complete. For LLM evaluators, provider fields and model
choices work in the same way as the LLM summary extractor. A fake response must use
the JSON shape expected by the evaluator; it is intended for deterministic workflow
testing rather than editorial scoring.

The fake LLM provider supports a fixed response for testing. OpenAI uses an
environment-variable name for the API key; saving does not require credentials or
contact the provider. Model availability and credentials are checked at runtime.

Static providers use **Add article** for title, URL, source, publication date,
authors (one per line), summary and content. Existing article metadata is retained.
Each provider, extractor or evaluator can be named, enabled or disabled, and
removed. Give multiple processors of the same type distinct processor keys. To
replace a processor type, add the replacement and remove the old entry.

## Draft, Save and Activate

Changes stay in a server-side draft until saved. Adding or removing entries and
updating LLM provider fields retains the other submitted fields. **Close draft**
discards unsaved edits. Drafts disappear on restart; the server retains at most 32
open drafts. Editing the same draft from multiple tabs produces a conflict rather
than accepting an outdated submission.

**Save** updates the source file, or creates the named file for a new configuration.
**Save as** creates a copy and refuses to overwrite an existing file. New files are
created in the deployment directory. Copies stay beside their source so relative
feed and publisher-template paths retain their meaning. If the source file changes
externally, reopen it before saving over it.

Saving does not activate the draft. **Use configuration** returns to workspace
selection; **Open workspace** loads it. If the active file was overwritten, further
workspace write actions pause until it is reopened. Saving is blocked while the
current workspace has a queued or running processing operation. Run one local
server against a database and avoid concurrent CLI operations when editing.

## Preservation and Scope

Extra settings and metadata are retained when editing an existing file. YAML comments and original
formatting are not preserved; saved YAML remains usable by the CLI.
Secret fields outside the editor stay on the server. URLs containing credentials or
query strings appear as an empty field with **Stored value retained**; leave that
field blank to preserve it, or enter a replacement URL.

New configurations can define publication details, providers, extractors,
evaluators, editorial policy, greedy optimisation and Markdown publishers.

## Configure Policy and Optimisation

**Editorial policy** records publication-level limits and eligible article statuses.
At present these values are descriptive configuration metadata: the greedy optimiser
does not enforce them. This is shown explicitly in the editor so that, for example,
changing the policy maximum article count is not mistaken for changing proposal
selection.

**Optimisation** controls proposal selection. Choose `greedy` and configure:

- maximum articles and an optional hard minimum relevance score as hard limits;
- relevance and reading-time targets as soft goals;
- topics to represent and a preferred maximum per source as soft preferences;
- weights to determine how strongly misses affect the objective value.

A relevance target does not reject an article. Use the hard minimum relevance score
when articles below a threshold must be excluded. The reading-time target is the
desired total, not a maximum: selections both above and below it incur a penalty.
Similarly, the per-source value is a preference rather than an exclusion rule.

Existing generic `constraints` and `maximise` values are retained when saving, but
the current greedy optimiser does not consume them. The editor therefore does not
present them as operational controls.

## Configure Publishing

Under **Publishers**, add a **Markdown** publisher to record Markdown as an
available output format. A display name and processor key are optional; the key is
useful when a configuration contains more than one publisher of the same type.

The optional template path may be absolute or relative to the configuration file's
folder. The editor preserves this setting, including when using **Save as**. The
current built-in Markdown renderer does not load custom templates, however, so the
field does not yet change the Markdown downloaded from the workspace or written by
the CLI. The editor says this explicitly to avoid presenting retained configuration
as an active rendering control.
