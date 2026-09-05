# Review and Revision in the Workspace

Start `editorial web` with your publication configuration and database. No existing issues
or reviews are required.

## Create the first issue proposal

Use **Operations** to ingest articles, extract metadata and evaluate them if you have not
already done so. Check **Configuration** for the active publication and optimisation settings.

Open **Issues** and choose **Generate issue proposal**, which is available even when no issues
exist. This saves an OptimisationRequest from the active configuration, runs the optimiser
against the same database, and opens the resulting proposal. Generation waits for completion.
Any failure is displayed on the Issues page, and the saved request remains in the database.

If no eligible articles are available, the optimiser may produce an empty proposal. Inspect
your Articles and evaluation evidence before generating another. Each generation creates a
new request and proposal, preserving earlier attempts.

## Submit a review

Review the proposal's selected articles, processor coverage and evidence before choosing
**Submit review**.

Enter your reviewer name and choose Approve, Reject, Needs changes or Comment. Comments,
findings and recommendations are optional. Submission creates an immutable Review and a
review-submitted WorkflowEvent. Free-text findings and recommendations are stored under
the `notes` key of their respective fields; existing structured CLI reviews remain visible.

## Example: reduce an oversized issue

Suppose the proposal contains twelve articles and you want an eight-article candidate.
Submit a Needs changes review with:

- Comments: "Reduce this issue to eight articles."
- Findings: "The current selection is too long."
- Recommendations: "Keep the strongest eight and compare the resulting coverage."

On the saved review, open **Advanced overrides** under **Create revision request** and
enter this Settings object:

```json
{"max_articles": 8}
```

The other override fields accept JSON objects too. Empty objects retain the active
configuration's defaults. Overrides merge at the top level, exactly as the CLI's revision
service does. Review prose is recorded as context; it is not automatically translated into
optimiser controls. The base is the workspace's active configuration, which may differ from
the historical request behind the original proposal.

Choose **Create revision request**. The new page exposes the stored strategy, settings,
constraints, goals and preferences. Choose **Generate candidate proposal** to execute it.
The request remains inspectable if generation fails, and can be retried. Generation waits
for completion and does not currently use the background processing monitor.

## Compare and decide

Each generated candidate has an issue link and **Compare with original** link. Inspect the
articles added or removed, ordering and evidence changes before submitting a new review on
the candidate. Approving it records a new decision; it does not overwrite the original
proposal or its needs-changes review.

Additional generations create additional proposals. All candidates are listed under the
same revision request. Requests also remain linked from their source review after refresh
or server restart. There is no review-edit or review-delete action.

The workspace remains intended for one local editor and has no authentication. Publication
composition in the browser is a separate roadmap phase.
