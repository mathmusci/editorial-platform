# Review And Revision

This tutorial explains how an editor can turn a `needs_changes` review into a new,
traceable OptimisationRequest and candidate IssueProposal without changing the original
proposal.

The workflow is:

```text
Original OptimisationRequest
    |
    v
Original IssueProposal
    |
    v
needs_changes Review
    |
    v
Revision OptimisationRequest
    |
    v
Candidate IssueProposal
    |
    v
Proposal comparison
    |
    v
New human review
```

Each item remains a separate immutable artefact. The review records judgement; it does not
silently modify settings or rerun the optimiser.

## Record requested changes

Inspect the proposal before reviewing it:

```bash
editorial proposal show <source-proposal-id> --db editorial.sqlite
editorial explain proposal <source-proposal-id> --db editorial.sqlite
```

Record the editorial judgement, findings, and recommendations:

```bash
editorial review create \
  --artefact-type issue_proposal \
  --artefact-id <source-proposal-id> \
  --reviewer "Editor" \
  --decision needs_changes \
  --comments "The issue is too long for this edition." \
  --finding reading_time_actual=24 \
  --finding reading_time_target=18 \
  --recommendation reading_time_target_minutes=18 \
  --recommendation max_articles=5 \
  --db editorial.sqlite
```

The command creates an append-only Review and records `review-submitted` on the original
proposal. It does not create an OptimisationRequest.

Only reviews with the `needs_changes` decision can create revisions. Approval means the
proposal may proceed, rejection ends that proposal's path, and a comment does not by itself
request a replacement proposal.

## Decide how to apply the review

Review findings and recommendations are deliberately generic dictionaries. They may contain
editorial language, article IDs, desired topics, or observations that do not map directly to
an optimiser parameter.

For that reason, `editorial review revise` does not automatically copy recommendation keys
into optimiser settings. The editor explicitly selects the changes to apply:

```bash
editorial review revise <review-id> \
  --config publication.yaml \
  --created-by "Editor" \
  --setting reading_time_target_minutes=18 \
  --setting max_articles=5 \
  --db editorial.sqlite
```

Override values use JSON syntax when possible:

```bash
--setting max_articles=5
--setting mandatory_terms='["statistics", "industry"]'
--constraint required_source='"BIS"'
--goal maximise='["relevance", "source_diversity"]'
--preference tone='"concise"'
```

Strings that are not valid JSON are stored as plain text. Repeatable `--setting`,
`--constraint`, `--goal`, and `--preference` options override the corresponding values from
the configuration. Unchanged values continue to come from the configuration.

## Inspect the revision request

Without `--run`, the command creates only the revision OptimisationRequest. It prints the
next command rather than running optimisation implicitly:

```bash
editorial optimisation-request show <revision-request-id> --db editorial.sqlite
editorial explain optimisation-request <revision-request-id> --db editorial.sqlite
```

The revision request records:

- `parent_request_id`: the request that produced the reviewed proposal, when available.
- `parent_proposal_id`: the reviewed proposal.
- `source_review_id`: the `needs_changes` review.
- Reviewer, decision, comments, findings, and recommendations.
- The configuration and explicit overrides chosen for the revision.

`editorial review show <review-id>` lists every linked revision request, so several
alternatives may be created from one review without losing their common origin.

The command records workflow events on three artefacts:

- `revision-requested` on the original IssueProposal.
- `revision-request-created` on the Review.
- `optimisation-request-created` on the new OptimisationRequest.

The original proposal's projected workflow state becomes `changes_requested`.

## Generate the candidate proposal

Run the request explicitly:

```bash
editorial optimisation-request run <revision-request-id> --db editorial.sqlite
```

The optimiser creates a new IssueProposal. It does not update or delete the original.

For a shorter development workflow, `--run` performs the request creation and optimiser run
in one command:

```bash
editorial review revise <review-id> \
  --config publication.yaml \
  --setting reading_time_target_minutes=18 \
  --setting max_articles=5 \
  --run \
  --db editorial.sqlite
```

The output includes the revision request ID, candidate proposal ID, and a ready-to-run
proposal comparison command.

## Compare before approving

Compare the reviewed proposal with its candidate replacement:

```bash
editorial proposal compare \
  <source-proposal-id> \
  <candidate-proposal-id> \
  --db editorial.sqlite
```

Look for:

1. Articles added, removed, or reordered.
2. Changes in reading time and relevance evidence.
3. The exact request settings changed by the editor.
4. Constraint targets, satisfaction, and penalties.
5. Missing or fallback evidence.

The candidate may have a lower objective value because the editorial policy changed. The
comparison supplies evidence; it does not declare that the candidate is better.

## Review the candidate

The original review does not transfer to the new proposal. Record a new decision:

```bash
editorial review create \
  --artefact-type issue_proposal \
  --artefact-id <candidate-proposal-id> \
  --reviewer "Editor" \
  --decision approve \
  --comments "The revision meets the reading-time target." \
  --db editorial.sqlite
```

If the candidate still needs work, record another `needs_changes` review and create another
revision request. The chain remains explicit:

```text
Proposal A -> Review A -> Request B -> Proposal B
Proposal B -> Review B -> Request C -> Proposal C
```

## Legacy proposals

A legacy proposal may not contain a valid `optimisation_request_id`. A revision can still be
created because the reviewed proposal provides useful lineage. In that case:

- `parent_proposal_id` is recorded.
- `parent_request_id` is unavailable.
- The review and all its recommendations remain recorded in request metadata.

This limitation is visible in command output and inspection rather than being inferred away.

## What revision does not do

`editorial review revise` does not:

- Change the Review or original IssueProposal.
- Interpret recommendations as optimiser settings automatically.
- Approve the candidate proposal.
- Copy the original review to the candidate.
- Create a Publication.
- Claim that the candidate is superior.

The editor remains responsible for applying the intended policy, comparing the result, and
recording the next decision.
