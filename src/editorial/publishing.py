from __future__ import annotations

from pathlib import Path
from uuid import UUID

from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    PublicationSection,
)


class PublicationBuilder:
    def build(
        self,
        proposal: IssueProposal,
        articles: list[Article],
        extractions: list[Extraction],
        evaluations: list[Evaluation],
        title: str,
        subtitle: str | None = None,
    ) -> Publication:
        article_ids = [article.id for article in articles]
        selected_article_ids = [
            article_id
            for article_id in proposal.article_ids
            if article_id in article_ids
        ]
        return Publication(
            proposal_id=proposal.id,
            title=title,
            subtitle=subtitle,
            sections=[
                PublicationSection(
                    heading="Selected articles",
                    article_ids=selected_article_ids,
                    metadata={"article_count": len(selected_article_ids)},
                )
            ],
            metadata={
                "proposal_id": str(proposal.id),
                "article_count": len(selected_article_ids),
                "optimiser": proposal.optimiser,
                "objective_value": proposal.objective_value,
                "extraction_count": len(extractions),
                "evaluation_count": len(evaluations),
            },
        )


class MarkdownPublisher:
    name = "markdown"
    version = "0.1"

    def __init__(self, articles: list[Article]):
        self.articles_by_id: dict[UUID, Article] = {
            article.id: article for article in articles
        }

    def publish(self, publication: Publication, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.render(publication), encoding="utf-8")

    def render(self, publication: Publication) -> str:
        lines = [f"# {publication.title}", ""]
        if publication.subtitle:
            lines.extend([publication.subtitle, ""])

        for section in publication.sections:
            lines.extend([f"## {section.heading}", ""])
            if section.summary:
                lines.extend([section.summary, ""])
            for article_id in section.article_ids:
                article = self.articles_by_id.get(article_id)
                if article is None:
                    lines.extend([f"- Missing article: {article_id}"])
                    continue
                lines.extend(self._article_lines(article))
            if lines[-1] != "":
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _article_lines(self, article: Article) -> list[str]:
        lines = [f"- **{article.title}**"]
        if article.summary:
            lines.append(f"  {article.summary}")
        source_parts = []
        if article.source:
            source_parts.append(article.source)
        if article.url:
            source_parts.append(str(article.url))
        if source_parts:
            lines.append(f"  Source: {' - '.join(source_parts)}")
        return lines
