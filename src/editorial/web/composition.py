from pathlib import Path
from uuid import UUID

from editorial.composition import PublicationComposition, PublicationCompositionService
from editorial.models import ReviewDecision, WorkflowEvent
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
    SQLiteWorkflowEventRepository,
)


class CompositionWorkspace:
    def __init__(self, db: Path):
        self.articles = SQLiteArticleRepository(db)
        self.extractions = SQLiteExtractionRepository(db)
        self.proposals = SQLiteIssueProposalRepository(db)
        self.publications = SQLitePublicationRepository(db)
        self.reviews = SQLiteReviewRepository(db)
        self.events = SQLiteWorkflowEventRepository(db)
        self.service = PublicationCompositionService(
            self.proposals,
            self.reviews,
            self.publications,
            self.articles,
            self.extractions,
        )

    def context(self, proposal_id: UUID, title: str, parent_id: UUID | None = None):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ValueError("Issue proposal not found")
        parent = self.publications.get(parent_id) if parent_id else None
        if parent_id and (parent is None or parent.proposal_id != proposal_id):
            raise ValueError("Parent publication must belong to this proposal")
        approvals = [
            r
            for r in self.reviews.list(
                artefact_type="issue_proposal", artefact_id=proposal_id
            )
            if r.decision == ReviewDecision.APPROVE
        ]
        articles = [self.articles.get(aid) for aid in proposal.article_ids]
        if any(a is None for a in articles):
            raise ValueError("Some proposal article records are missing")
        values = {
            "title": parent.title if parent else title,
            "subtitle": (parent.subtitle or "") if parent else "",
            "introduction": (parent.introduction or "") if parent else "",
            "created_by": (parent.created_by or "") if parent else "",
            "approved_review_id": str(parent.approved_review_id)
            if parent and parent.approved_review_id
            else (str(approvals[-1].id) if approvals else ""),
            "parent_id": str(parent_id) if parent_id else "",
        }
        section_count = max(len(articles), len(parent.sections) if parent else 0, 1)
        for i in range(section_count):
            section = (
                parent.sections[i] if parent and i < len(parent.sections) else None
            )
            values.update(
                {
                    f"heading_{i}": section.heading
                    if section
                    else ("Selected articles" if i == 0 else ""),
                    f"intro_{i}": (section.introduction or "") if section else "",
                    f"section_order_{i}": str(i + 1),
                }
            )
        for i, article in enumerate(articles):
            values.update(
                {
                    f"section_{i}": "0",
                    f"order_{i}": str(i + 1),
                    f"title_{i}": article.title,
                    f"summary_{i}": "",
                    f"source_{i}": "",
                    f"reason_{i}": "",
                }
            )
            if parent:
                for si, section in enumerate(parent.sections):
                    for ai, item in enumerate(section.articles):
                        if item.article_id == article.id:
                            values.update(
                                {
                                    f"section_{i}": str(si),
                                    f"order_{i}": str(ai + 1),
                                    f"title_{i}": item.title or article.title,
                                    f"summary_{i}": item.summary or "",
                                    f"source_{i}": str(
                                        item.summary_extraction_id or ""
                                    ),
                                }
                            )
                for excluded in parent.exclusions:
                    if excluded.article_id == article.id:
                        values.update(
                            {f"section_{i}": "excluded", f"reason_{i}": excluded.reason}
                        )
        return dict(
            proposal=proposal,
            parent=parent,
            approvals=approvals,
            articles=articles,
            section_count=section_count,
            values=values,
            summaries={
                a.id: [
                    e
                    for e in self.extractions.list(article_id=a.id)
                    if e.kind == "summary"
                ]
                for a in articles
            },
        )

    def save(self, context, form):
        sections = {i: [] for i in range(context["section_count"])}
        excluded = []
        parent = context["parent"]
        previous = (
            {a.article_id: a for s in parent.sections for a in s.articles}
            if parent
            else {}
        )
        for i, article in enumerate(context["articles"]):
            selected = form.get(f"section_{i}", "")
            if selected == "excluded":
                excluded.append(
                    dict(
                        article_id=article.id,
                        reason=form.get(f"reason_{i}", "").strip(),
                    )
                )
                continue
            section_id = int(selected)
            if section_id not in sections:
                raise ValueError("Select a valid section for each article")
            order = int(form.get(f"order_{i}", ""))
            if order < 1:
                raise ValueError("Article order must be positive")
            old = previous.get(article.id)
            sections[section_id].append(
                (
                    order,
                    i,
                    dict(
                        article_id=article.id,
                        title=form.get(f"title_{i}", "").strip() or None,
                        summary=form.get(f"summary_{i}") or None,
                        summary_extraction_id=form.get(f"source_{i}") or None,
                        metadata=old.metadata if old else {},
                    ),
                )
            )
        ordered = []
        for si, items in sections.items():
            if not items:
                continue
            order = int(form.get(f"section_order_{si}", ""))
            if order < 1:
                raise ValueError("Section order must be positive")
            ordered.append(
                (
                    order,
                    si,
                    dict(
                        heading=form.get(f"heading_{si}", "").strip(),
                        introduction=form.get(f"intro_{si}") or None,
                        articles=[a for _, _, a in sorted(items)],
                        metadata=parent.sections[si].metadata
                        if parent and si < len(parent.sections)
                        else {},
                    ),
                )
            )
        composition = PublicationComposition(
            title=form.get("title", "").strip(),
            subtitle=form.get("subtitle") or None,
            introduction=form.get("introduction") or None,
            sections=[s for _, _, s in sorted(ordered)],
            excluded=excluded,
            metadata=parent.metadata if parent else {},
        )
        publication = self.service.compose(
            context["proposal"].id,
            UUID(form.get("approved_review_id", "")),
            composition,
            created_by=form.get("created_by", "").strip() or None,
            parent_publication_id=parent.id if parent else None,
            composition_source="workspace",
        )
        self.events.insert(
            WorkflowEvent(
                artefact_type="publication",
                artefact_id=publication.id,
                event_type="publication-created",
                actor=publication.created_by,
                payload={
                    "proposal_id": str(publication.proposal_id),
                    "approved_review_id": str(publication.approved_review_id),
                    **({"parent_publication_id": str(parent.id)} if parent else {}),
                },
            )
        )
        return publication
