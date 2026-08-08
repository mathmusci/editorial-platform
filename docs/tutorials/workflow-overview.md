# Workflow Overview

This tutorial explains how to inspect the state of one editorial issue without reconstructing
its history from separate commands. The overview is anchored to an explicit IssueProposal
and derives its result from immutable artefacts and WorkflowEvents.

```text
Articles -> Extractions -> Evaluations -> IssueProposal -> Review -> Publication -> Render
                                      \_______________________________________________/
                                                    |
                                             workflow overview
```

The command does not run processors, change workflow state, or choose a “latest” proposal.

## Run the overview

Use the same publication configuration and database that produced the proposal:

```bash
editorial workflow overview \
  --config examples/bis/publication.yaml \
  --proposal-id <proposal-id> \
  --db editorial.sqlite
```

The proposal ID is required. This makes repeated runs deterministic even when the database
contains several optimisation attempts or publication revisions.

## Read the identity

The first panel identifies:

- The configured publication.
- The IssueProposal and its originating OptimisationRequest, when available.
- The number of selected articles.
- The overall derived status.
- The proposal state projected from its WorkflowEvents.

The derived status and event state answer different questions. The event state reports the
proposal's recorded event history. The overall status also considers Reviews, approved
Publications, and rendered outputs linked to the proposal.

## Read the issue stages

The stage table contains:

1. **Articles**: whether every selected Article record still exists.
2. **Extraction**: configured extraction operations present for selected articles.
3. **Evaluation**: configured evaluation operations present for selected articles.
4. **Proposal**: the stored optimiser result and objective value.
5. **Review**: the latest recorded Review decision.
6. **Composition**: a Publication linked to that exact approval Review.
7. **Rendering**: a recorded rendered output for that Publication.

Every row includes an existing inspection or explanation command. The overview is therefore
a navigation surface over stored evidence, not a replacement for detailed inspection.

Possible stage states are:

- `complete`: the expected stored evidence exists.
- `incomplete`: one or more expected records are missing.
- `pending`: the editorial step has not happened yet.
- `changes_requested`: the latest Review requests a revision.
- `rejected`: the latest Review rejects the proposal.
- `not_configured`: the supplied configuration enables no processors for that evidence type.

## Understand coverage

Extraction and evaluation coverage use configured processor identities, not only artefact
kinds. If two summary extractors or relevance evaluators are configured, each
article-processor operation is counted independently.

For example, a proposal with five articles, two extractors, and three evaluators expects:

```text
Extraction operations: 5 x 2 = 10
Evaluation operations: 5 x 3 = 15
```

The coverage tables show present and missing operations by configured processor. They do not
invoke local Ollama models or external providers.

## Follow outstanding actions

The final table contains only actions that can be derived from current artefacts. Common
examples include:

- Resume missing extraction or evaluation operations.
- Review a proposal with no Review.
- Create or run a revision request after `needs_changes`.
- Compare a revised candidate with the reviewed proposal.
- Compose a proposal after approval.
- Render a composed Publication.

Evidence resume commands include every proposal Article as `--article-id`, keeping the work
scoped to the issue being inspected.

When a rendered Publication has complete evidence coverage, the overview reports no
outstanding actions. When rendering exists despite evidence gaps, the overall status is
`rendered_with_evidence_gaps` and the missing evidence remains visible.

## Review and revision example

After a `needs_changes` Review, run the overview again:

```bash
editorial workflow overview \
  --config publication.yaml \
  --proposal-id <reviewed-proposal-id> \
  --db editorial.sqlite
```

The next action depends on stored lineage:

```text
No revision request       -> create one with review revise
Revision request only     -> run it
Candidate proposal exists -> compare it with the reviewed proposal
```

Once the optimiser creates the candidate, use the candidate proposal ID for its own overview.
The original overview remains a factual view of the original proposal's history.

## Approval and publication example

For an approved proposal, the overview considers composition complete only when a Publication
records the latest approval Review ID. A Publication created from an older approval does not
satisfy a newer approval.

```text
Latest Review is approve
    |
    +-- no matching Publication -> compose
    |
    +-- matching Publication, no output -> render
    |
    +-- matching rendered Publication -> complete
```

This rule prevents an old Publication from silently representing a later editorial decision.

## What the overview does not do

`editorial workflow overview` does not:

- Select a proposal implicitly.
- Store a mutable issue status.
- Run extraction, evaluation, optimisation, composition, or rendering.
- Decide whether an evidence gap should block approval.
- Replace detailed inspection or explanation commands.
- Infer editorial reasoning that was not recorded.

It summarises what exists, identifies what is missing, and provides the next inspectable path.
