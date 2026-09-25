# Publication Composition in the Workspace

This walkthrough starts with an issue proposal containing articles and an **Approve**
review. If you have neither yet, follow [Review and Revision](review-revision-workspace.md)
to generate a proposal, inspect its evidence, and submit an approval.

## Compose an edition

Open the proposal under **Proposals** and choose **Compose publication**. Select the approval
and enter the editor name, publication title, subtitle and introduction. Without an approval,
the page links back to the review form. Empty proposals cannot be composed.

Suppose the proposal contains three articles and you want two sections:

1. Name Section 1 "Industry" and give it order `1`.
2. Expand Section 2, name it "Forecasting" and give it order `2`.
3. Assign the first two articles to Section 1, with article orders `1` and `2`.
4. Assign the third article to Section 2, with article order `1`.

Section numbers identify the available slots; order fields determine their order in the
saved publication. Unused slots are ignored. Tied order values retain slot order for
sections and proposal order for articles. There can be up to one section per article.

Each article has an editorial title, a summary-source selector and an optional editorial
summary override. Leave the override blank to use the chosen source: either the Article's
summary or a stored summary Extraction. An override takes precedence over the source text.
Selected extraction IDs remain attached for provenance and must belong to that Article.
Article links open the evidence page separately so you can inspect summaries before choosing.

To omit an article, choose **Exclude** for its placement and supply an exclusion reason.
At least one article must remain included. Every included section needs a heading.

## Save, inspect and render

Choose **Save publication**. The existing composition service validates approval, coverage
and summary provenance. Invalid input returns to the form with your text retained.
The resulting Publication page previews the saved titles, introductions, sections, article
summaries and exclusions, with links to the proposal and approving review.

Choose **Download Markdown** to invoke the existing Markdown renderer. The response is a
browser download; its destination is controlled by your browser. A rendering WorkflowEvent
records Markdown delivery without claiming a server-side file was written.

## Make another version

Choose **Edit as new version** on a Publication. The form starts with its saved composition.
Saving creates a new Publication with a parent link; the original remains unchanged.
Both versions remain accessible from their publication pages, preserving their approvals,
source evidence references and creation events.

The form is not an autosaved draft. Save before closing it. When editing, saved summary
text is prefilled as an override to preserve the existing edition. Clear that override
explicitly if you want a newly selected summary source to supply the text.
