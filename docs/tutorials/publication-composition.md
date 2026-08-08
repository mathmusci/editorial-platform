# Publication Composition

This tutorial explains how an editor turns an approved IssueProposal into an ordered,
reproducible Publication. Composition is a manual editorial step: it records how selected
articles should be presented without changing the proposal or invoking an LLM.

The workflow is:

```text
IssueProposal
    |
    v
approve Review
    |
    v
Composition YAML
    |
    v
immutable Publication
    |
    v
Markdown rendering
```

## Approve the proposal

Inspect and explain the proposal before deciding whether it is ready:

```bash
editorial proposal show <proposal-id> --db editorial.sqlite
editorial explain proposal <proposal-id> --db editorial.sqlite
```

Record an explicit approval:

```bash
editorial review create \
  --artefact-type issue_proposal \
  --artefact-id <proposal-id> \
  --reviewer "Editor" \
  --decision approve \
  --comments "Ready for composition." \
  --db editorial.sqlite
```

Keep the resulting Review ID. Composition requires that exact Review to target the selected
IssueProposal and have the `approve` decision. A comment, rejection, or `needs_changes`
review cannot authorise publication composition.

## Inspect the available content

The proposal shows the selected article IDs and their order:

```bash
editorial proposal show <proposal-id> --db editorial.sqlite
```

Inspect an article and its Extractions before choosing the text to publish:

```bash
editorial article show <article-id> --db editorial.sqlite
editorial extraction list --article-id <article-id> --db editorial.sqlite
editorial extraction show <summary-extraction-id> --db editorial.sqlite
```

A summary Extraction is optional. When `summary_extraction_id` is supplied, composition
validates that the Extraction belongs to the same article and has kind `summary`.

## Write the composition file

Create `issue-composition.yaml`:

```yaml
title: BIS Newsletter
subtitle: August 2026

introduction: >
  This issue examines monetary policy, market resilience, and new approaches
  to financial data.

sections:
  - heading: Lead analysis
    introduction: The principal developments this month.
    articles:
      - article_id: 11111111-1111-1111-1111-111111111111
        title: What the latest policy decision means
        summary_extraction_id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa

      - article_id: 22222222-2222-2222-2222-222222222222
        summary: >
          An editor-written summary can be stored directly in the Publication.

  - heading: Data and methods
    articles:
      - article_id: 33333333-3333-3333-3333-333333333333

excluded:
  - article_id: 44444444-4444-4444-4444-444444444444
    reason: Substantially duplicates the lead analysis.

metadata:
  edition: monthly
```

The order of `sections` becomes publication section order. The order of `articles` within a
section becomes article order.

Each proposal article must appear exactly once: either under one section or under
`excluded`. Exclusions require a reason. This makes omission an explicit editorial decision
rather than an accidental side effect.

For each included article:

- `article_id` is required and must belong to the proposal.
- `title` optionally replaces the source headline.
- `summary` optionally supplies editor-written publication text.
- `summary_extraction_id` optionally selects stored summary evidence.
- When neither summary field is supplied, the current Article summary is used.

If both `summary` and `summary_extraction_id` are present, the edited summary is published
and the Extraction remains recorded as its source provenance.

## Compose the publication

```bash
editorial publication compose \
  --proposal-id <proposal-id> \
  --approved-review-id <approval-review-id> \
  --composition issue-composition.yaml \
  --created-by "Editor" \
  --db editorial.sqlite
```

The command reports the Publication ID, section count, included article count, and excluded
article count. It stores `publication-created` with the editor, proposal, and approval
lineage.

Composition validates all input before storing anything. It rejects:

- A missing proposal, Review, Article, parent Publication, or summary Extraction.
- A Review that does not approve the selected proposal.
- An article outside the proposal.
- Duplicate placement or duplicate exclusion.
- An article that is both included and excluded.
- A proposal article that is not accounted for.
- A summary Extraction belonging to another article or another extraction kind.

## Inspect the result

```bash
editorial publication show <publication-id> --db editorial.sqlite
editorial explain publication <publication-id> --db editorial.sqlite
```

Inspection shows the issue and section introductions, publication-time titles and summaries,
summary Extraction IDs, exclusions and reasons, approving editor, parent Publication, source
evidence, workflow history, and rendered outputs.

## Why content is snapshotted

The Publication stores the title, summary, source, and URL used for every included article.
It also retains the source Article ID and optional summary Extraction ID.

This separates content from provenance:

```text
Article and Extraction IDs -> where the content came from
Publication snapshots      -> exactly what the editor chose to publish
```

If an Article is later re-ingested or re-extracted, rendering the stored Publication still
produces the same editorial content.

## Revise a composition

Publications are append-only. To revise one, update the composition YAML and create another
Publication linked to its parent:

```bash
editorial publication compose \
  --proposal-id <proposal-id> \
  --approved-review-id <approval-review-id> \
  --composition revised-composition.yaml \
  --created-by "Editor" \
  --parent-publication-id <original-publication-id> \
  --db editorial.sqlite
```

The original Publication remains unchanged. `publication show` exposes both parent and
revised Publication links.

## Render Markdown

```bash
editorial publish markdown \
  --publication-id <publication-id> \
  --output newsletter.md \
  --db editorial.sqlite
```

Rendering uses the Publication snapshots, including editorial headlines, introductions, and
selected summaries. It does not regenerate content or read a newer summary into the issue.

## Scope

Publication composition does not automatically generate sections, write introductions with
an LLM, create additional rendering formats, or distribute the rendered publication. These
remain separate future candidates requiring design and prioritisation.
