from __future__ import annotations

from pathlib import Path
from uuid import UUID

from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    Publication,
    PublicationArticle,
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
        articles_by_id = {article.id: article for article in articles}
        selected_article_ids = [
            article_id
            for article_id in proposal.article_ids
            if article_id in articles_by_id
        ]
        return Publication(
            proposal_id=proposal.id,
            title=title,
            subtitle=subtitle,
            sections=[
                PublicationSection(
                    heading="Selected articles",
                    articles=[
                        self._snapshot_article(articles_by_id[article_id])
                        for article_id in selected_article_ids
                    ],
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

    def _snapshot_article(self, article: Article) -> PublicationArticle:
        return PublicationArticle(
            article_id=article.id,
            title=article.title,
            summary=article.summary,
            source=article.source,
            url=str(article.url) if article.url else None,
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
        if publication.introduction:
            lines.extend([publication.introduction, ""])

        for section in publication.sections:
            lines.extend([f"## {section.heading}", ""])
            if section.introduction:
                lines.extend([section.introduction, ""])
            for item in section.articles:
                article = self.articles_by_id.get(item.article_id)
                if item.title is None and article is None:
                    lines.extend([f"- Missing article: {item.article_id}"])
                    continue
                lines.extend(self._article_lines(item, article))
            if lines[-1] != "":
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _article_lines(
        self, item: PublicationArticle, article: Article | None
    ) -> list[str]:
        if item.title is not None:
            title = item.title
            summary = item.summary
            source = item.source
            url = item.url
        else:
            if article is None:
                raise ValueError(f"Article record not available: {item.article_id}")
            title = article.title
            summary = article.summary
            source = article.source
            url = str(article.url or "")

        lines = [f"- **{title}**"]
        if summary:
            lines.append(f"  {summary}")
        source_parts = []
        if source:
            source_parts.append(source)
        if url:
            source_parts.append(url)
        if source_parts:
            lines.append(f"  Source: {' - '.join(source_parts)}")
        return lines
