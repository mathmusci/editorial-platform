# Configuration Editor

The first stage covers publication details, content providers and extractors.
Start with `editorial web`, then choose **New configuration**, or select an existing
YAML file and choose **Edit selected configuration**. In an open workspace, choose
**Configuration > Edit configuration**.

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

The fake LLM provider supports a fixed response for testing. OpenAI uses an
environment-variable name for the API key; saving does not require credentials or
contact the provider. Model availability and credentials are checked at runtime.

Static providers use **Add article** for title, URL, source, publication date,
authors (one per line), summary and content. Existing article metadata is retained.
Each provider or extractor can be named, enabled or disabled, and removed. Give
multiple extractors of the same type distinct processor keys. To replace a content
provider or extractor type, add the replacement and remove the old entry.

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

Evaluator configuration, editorial policy, optimisation, publishers, extra settings
and metadata are retained when editing an existing file. YAML comments and original
formatting are not preserved; saved YAML remains usable by the CLI.
Secret fields outside the editor stay on the server. URLs containing credentials or
query strings appear as an empty field with **Stored value retained**; leave that
field blank to preserve it, or enter a replacement URL.

New configurations initially contain publication details and the providers and
extractors you add. They do not yet define evaluator or publication-selection
settings. For a complete pipeline today, edit or copy an existing complete
configuration. Later stages add evaluator, editorial-policy and optimisation
editing, followed by publishers.
