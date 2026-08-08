from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from editorial.models import (
    Article,
    Extraction,
    IssueProposal,
    Publication,
    PublicationArticle,
    PublicationExclusion,
    PublicationSection,
    Review,
    ReviewDecision,
)
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteExtractionRepository,
    SQLiteIssueProposalRepository,
    SQLitePublicationRepository,
    SQLiteReviewRepository,
)


class CompositionArticle(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: UUID
    title: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    summary_extraction_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompositionSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str = Field(min_length=1)
    introduction: str | None = None
    articles: list[CompositionArticle] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompositionExclusion(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: UUID
    reason: str = Field(min_length=1)


class PublicationComposition(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    subtitle: str | None = None
    introduction: str | None = None
    sections: list[CompositionSection] = Field(min_length=1)
    excluded: list[CompositionExclusion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_publication_composition(path: str | Path) -> PublicationComposition:
    composition_path = Path(path)
    try:
        with composition_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ValueError(
            f"Could not read composition file {composition_path}: {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid composition YAML in {composition_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError("Publication composition must be a YAML object")
    try:
        return PublicationComposition.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid publication composition: {exc}") from exc


class PublicationCompositionService:
    def __init__(
        self,
        proposals: SQLiteIssueProposalRepository,
        reviews: SQLiteReviewRepository,
        publications: SQLitePublicationRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
    ):
        self.proposals = proposals
        self.reviews = reviews
        self.publications = publications
        self.articles = articles
        self.extractions = extractions

    def compose(
        self,
        proposal_id: UUID,
        approved_review_id: UUID,
        composition: PublicationComposition,
        *,
        created_by: str | None = None,
        parent_publication_id: UUID | None = None,
        composition_source: str | None = None,
    ) -> Publication:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ValueError(f"Issue proposal not found: {proposal_id}")
        review = self._approved_review(approved_review_id, proposal)
        self._validate_parent(parent_publication_id)
        self._validate_coverage(proposal, composition)

        proposal_article_ids = set(proposal.article_ids)
        articles_by_id = {
            article.id: article
            for article in self.articles.list()
            if article.id in proposal_article_ids
        }
        missing_articles = proposal_article_ids - set(articles_by_id)
        if missing_articles:
            raise ValueError(
                "Article records not found: " + self._format_ids(missing_articles)
            )

        publication = Publication(
            proposal_id=proposal.id,
            approved_review_id=review.id,
            parent_publication_id=parent_publication_id,
            created_by=created_by,
            title=composition.title,
            subtitle=composition.subtitle,
            introduction=composition.introduction,
            sections=[
                self._build_section(section, articles_by_id)
                for section in composition.sections
            ],
            exclusions=[
                PublicationExclusion(
                    article_id=exclusion.article_id,
                    reason=exclusion.reason,
                )
                for exclusion in composition.excluded
            ],
            metadata={
                **composition.metadata,
                **(
                    {"composition_source": composition_source}
                    if composition_source
                    else {}
                ),
                "proposal_id": str(proposal.id),
                "approved_review_id": str(review.id),
                "article_count": sum(
                    len(section.articles) for section in composition.sections
                ),
                "excluded_article_count": len(composition.excluded),
                "optimiser": proposal.optimiser,
                "objective_value": proposal.objective_value,
            },
        )
        self.publications.insert(publication)
        return publication

    def _approved_review(self, review_id: UUID, proposal: IssueProposal) -> Review:
        review = self.reviews.get(review_id)
        if review is None:
            raise ValueError(f"Review not found: {review_id}")
        if (
            review.artefact_type != "issue_proposal"
            or review.artefact_id != proposal.id
        ):
            raise ValueError("Approved review must review the selected issue proposal")
        if review.decision != ReviewDecision.APPROVE:
            raise ValueError("Publication composition requires an approve review")
        return review

    def _validate_parent(self, parent_publication_id: UUID | None) -> None:
        if (
            parent_publication_id is not None
            and self.publications.get(parent_publication_id) is None
        ):
            raise ValueError(f"Parent publication not found: {parent_publication_id}")

    def _validate_coverage(
        self, proposal: IssueProposal, composition: PublicationComposition
    ) -> None:
        included = [
            article.article_id
            for section in composition.sections
            for article in section.articles
        ]
        excluded = [item.article_id for item in composition.excluded]
        duplicate_included = self._duplicates(included)
        duplicate_excluded = self._duplicates(excluded)
        if duplicate_included:
            raise ValueError(
                "Articles included more than once: "
                + self._format_ids(duplicate_included)
            )
        if duplicate_excluded:
            raise ValueError(
                "Articles excluded more than once: "
                + self._format_ids(duplicate_excluded)
            )

        included_ids = set(included)
        excluded_ids = set(excluded)
        overlap = included_ids & excluded_ids
        if overlap:
            raise ValueError(
                "Articles cannot be both included and excluded: "
                + self._format_ids(overlap)
            )

        proposal_ids = set(proposal.article_ids)
        outside_proposal = (included_ids | excluded_ids) - proposal_ids
        if outside_proposal:
            raise ValueError(
                "Composition contains articles outside the proposal: "
                + self._format_ids(outside_proposal)
            )
        unaccounted = proposal_ids - included_ids - excluded_ids
        if unaccounted:
            raise ValueError(
                "Proposal articles must be included or explicitly excluded: "
                + self._format_ids(unaccounted)
            )

    def _build_section(
        self, section: CompositionSection, articles_by_id: dict[UUID, Article]
    ) -> PublicationSection:
        return PublicationSection(
            heading=section.heading,
            introduction=section.introduction,
            articles=[
                self._build_article(item, articles_by_id[item.article_id])
                for item in section.articles
            ],
            metadata=section.metadata,
        )

    def _build_article(
        self, item: CompositionArticle, article: Article
    ) -> PublicationArticle:
        extraction = self._summary_extraction(item, article)
        summary = item.summary
        if summary is None and extraction is not None:
            extracted_summary = extraction.payload.get("summary")
            if not isinstance(extracted_summary, str) or not extracted_summary:
                raise ValueError(
                    f"Summary extraction {extraction.id} has no text summary"
                )
            summary = extracted_summary
        if summary is None:
            summary = article.summary

        return PublicationArticle(
            article_id=article.id,
            title=item.title or article.title,
            summary=summary,
            source=article.source,
            url=str(article.url) if article.url else None,
            summary_extraction_id=extraction.id if extraction else None,
            metadata=item.metadata,
        )

    def _summary_extraction(
        self, item: CompositionArticle, article: Article
    ) -> Extraction | None:
        if item.summary_extraction_id is None:
            return None
        extraction = self.extractions.get(item.summary_extraction_id)
        if extraction is None:
            raise ValueError(
                f"Summary extraction not found: {item.summary_extraction_id}"
            )
        if extraction.article_id != article.id:
            raise ValueError(
                f"Summary extraction {extraction.id} does not belong to article "
                f"{article.id}"
            )
        if extraction.kind != "summary":
            raise ValueError(f"Extraction {extraction.id} is not a summary extraction")
        return extraction

    @staticmethod
    def _duplicates(values: list[UUID]) -> set[UUID]:
        seen: set[UUID] = set()
        duplicates: set[UUID] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        return duplicates

    @staticmethod
    def _format_ids(values: set[UUID]) -> str:
        return ", ".join(sorted(str(value) for value in values))
