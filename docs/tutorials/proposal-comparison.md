# Comparing Issue Proposals

This tutorial explains how to compare two stored IssueProposals before deciding which one
should move forward to editorial review or publication.

Proposal comparison answers a practical question:

> What changed between these two proposed issues, and what stored evidence explains the
> change?

It does not rerun extraction, evaluation, or optimisation. It reads the proposals and their
linked artefacts from the database.

## Why compare proposals

Every optimiser run creates a new immutable OptimisationRequest and IssueProposal. This is
deliberate: a revised issue does not overwrite the previous suggestion. Over time, however,
an editor may have several proposals produced with different targets, evidence, or optimiser
settings.

For example:

```text
Base request
  max_articles: 6
  reading_time_target_minutes: 18
      |
      v
Base proposal
  Articles A, B, C, D

Candidate request
  max_articles: 5
  reading_time_target_minutes: 15
  parent: base request and proposal
      |
      v
Candidate proposal
  Articles B, A, E
```

The objective values alone do not explain this change. The editor also needs to see that C
and D were removed, E was added, B moved ahead of A, the reading-time target changed, and
the constraint penalties changed.

## Prepare the evidence

Run ingestion, extraction, and evaluation before optimisation:

```bash
editorial ingest \
  --config examples/bis/publication.yaml \
  --db bis-proposals.sqlite

editorial extract \
  --config examples/bis/publication.yaml \
  --db bis-proposals.sqlite \
  --missing-only \
  --progress

editorial evaluate \
  --config examples/bis/publication.yaml \
  --db bis-proposals.sqlite \
  --missing-only \
  --progress
```

The greedy optimiser currently uses relevance Evaluations and reading-time Extractions. It
stores the selected articles' relevance, reading time, source, and mandatory-term matches in
the proposal metadata. These proposal-time snapshots are important when proposals are
compared later.

## Create the base proposal

Create an immutable request from the base configuration:

```bash
editorial optimisation-request create \
  --config examples/bis/publication.yaml \
  --created-by "Editor" \
  --db bis-proposals.sqlite
```

The command prints a request ID. Run it:

```bash
editorial optimisation-request run <base-request-id> \
  --db bis-proposals.sqlite
```

List the resulting proposals and record the base proposal ID:

```bash
editorial proposal list --db bis-proposals.sqlite
editorial proposal show <base-proposal-id> --db bis-proposals.sqlite
```

## Create a candidate proposal

Copy the publication configuration and change only the editorial policy being tested. For
example, reduce the reading-time target:

```yaml
optimisation:
  strategy: greedy
  settings:
    max_articles: 6
    relevance_target_score: 40
    reading_time_target_minutes: 15
    mandatory_terms: [statistics, industry]
```

Create the candidate request with explicit lineage to the base request and proposal:

```bash
editorial optimisation-request create \
  --config publication-candidate.yaml \
  --created-by "Editor" \
  --parent-request-id <base-request-id> \
  --parent-proposal-id <base-proposal-id> \
  --db bis-proposals.sqlite
```

Run the candidate request and record its proposal ID:

```bash
editorial optimisation-request run <candidate-request-id> \
  --db bis-proposals.sqlite

editorial proposal list --db bis-proposals.sqlite
```

Parent IDs document editorial intent, but comparison does not require the two proposals to
belong to the same lineage. Any two stored proposals can be compared.

## Compare the proposals

Pass the earlier proposal first and the proposed replacement second:

```bash
editorial proposal compare \
  <base-proposal-id> \
  <candidate-proposal-id> \
  --db bis-proposals.sqlite
```

The report contains five sections.

### Proposal summary and provenance

The summary reports shared, added, removed, and moved article counts. It also shows the
objective change and known reading-time totals.

The provenance table identifies each proposal's OptimisationRequest, publication, strategy,
optimiser, and optimiser version. A missing request is reported as an evidence gap rather
than silently ignored.

### Article changes

Each article is classified as:

- `shared`: selected by both proposals.
- `shared, moved`: selected by both, but in a different position.
- `added`: selected only by the candidate.
- `removed`: selected only by the base.

Base and candidate evidence are shown separately. This matters when the same article was
selected with different relevance or reading-time evidence.

### Optimisation request changes

The request table shows only changed fields. Nested settings are displayed with paths such
as:

```text
settings.reading_time_target_minutes
settings.source_diversity_max_per_source
goals.maximise
```

This separates a change in editorial intent from a change caused by source evidence.

### Constraint outcomes

Constraint results are classified as `unchanged`, `changed`, `added`, or `removed`. The
report compares satisfaction, observed value, target, and penalty.

An objective value should not be interpreted in isolation when request settings or
constraints differ. A higher value under one policy is not automatically better than a
lower value under another policy.

### Evidence gaps

The report explicitly identifies evidence it cannot verify, including:

- A proposal without a linked OptimisationRequest.
- An article record that no longer exists.
- Missing relevance or reading-time evidence.
- A legacy proposal without proposal-time evidence snapshots.

For a legacy proposal, comparison falls back to the article's current stored evidence and
labels it `Current stored evidence`. That evidence is useful for inspection, but it is not
claimed to be the evidence used when the proposal was originally generated.

## Interpreting a larger change

Suppose the candidate removes two high-scoring articles, adds one lower-scoring article, and
reduces the reading-time penalty. The comparison does not declare a winner. It gives the
editor the facts needed to ask:

1. Was the shorter issue an explicit editorial goal?
2. Did the removed articles fail a new constraint?
3. Does the added article improve mandatory-term or source coverage?
4. Is the lower objective expected because the policy changed?
5. Is any conclusion based on current fallback evidence rather than proposal-time evidence?

The answer may be to approve the candidate, retain the base proposal, or create another
OptimisationRequest. Comparison remains inspection, not approval.

## What comparison does not do

`editorial proposal compare` does not:

- Call an LLM.
- Rerun an optimiser.
- Change either proposal.
- Copy a review decision.
- Approve a proposal.
- Create a Publication.
- Infer which proposal is editorially superior.

The next workflow step remains an explicit human review. If changes are requested, create a
new OptimisationRequest with parent request and proposal IDs, generate another proposal, and
compare again.
