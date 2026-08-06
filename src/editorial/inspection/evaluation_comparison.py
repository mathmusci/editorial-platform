from __future__ import annotations

from typing import Iterable, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from editorial.models import Article, Evaluation, Extraction
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


SUMMARY_QUALITY_DIMENSIONS = (
    "faithfulness",
    "coverage",
    "clarity",
    "concision",
)


class SummaryQualityScores(BaseModel):
    faithfulness: float | None = None
    coverage: float | None = None
    clarity: float | None = None
    concision: float | None = None


class SummaryQualityComparisonResult(BaseModel):
    evaluator: str
    status: Literal["present", "missing"]
    evaluation_id: UUID | None = None
    score: float | None = None
    confidence: float | None = None
    dimensions: SummaryQualityScores = Field(default_factory=SummaryQualityScores)
    issues: list[str] = Field(default_factory=list)
    summary_extractor: str | None = None
    summary_provider: str | None = None
    summary_model: str | None = None
    evaluator_provider: str | None = None
    evaluator_model: str | None = None


class ArticleSummaryQualityComparison(BaseModel):
    article_id: UUID
    article_title: str
    article_source: str | None = None
    results: list[SummaryQualityComparisonResult]


class SummaryQualityAggregate(BaseModel):
    evaluator: str
    articles: int
    evaluated: int
    missing: int
    average_score: float | None = None
    average_confidence: float | None = None
    average_dimensions: SummaryQualityScores = Field(
        default_factory=SummaryQualityScores
    )
    issue_count: int = 0
    summary_providers: list[str] = Field(default_factory=list)
    summary_models: list[str] = Field(default_factory=list)
    evaluator_providers: list[str] = Field(default_factory=list)
    evaluator_models: list[str] = Field(default_factory=list)


class SummaryQualityComparisonReport(BaseModel):
    evaluator_keys: list[str]
    articles_selected: int
    expected_evaluations: int
    present: int
    missing: int
    aggregates: list[SummaryQualityAggregate]
    articles: list[ArticleSummaryQualityComparison]


class SummaryQualityComparisonService:
    def __init__(
        self,
        evaluations: SQLiteEvaluationRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
    ):
        self.evaluations = evaluations
        self.articles = articles
        self.extractions = extractions

    def compare(
        self,
        *,
        evaluator_keys: Iterable[str] | None = None,
        article_ids: Iterable[UUID] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> SummaryQualityComparisonReport:
        if limit is not None and limit <= 0:
            raise ValueError("Comparison limit must be a positive integer")
        if offset < 0:
            raise ValueError("Comparison offset must be zero or greater")

        quality_evaluations = [
            evaluation
            for evaluation in self.evaluations.list()
            if evaluation.kind == "summary_quality"
        ]
        selected_keys = self._select_evaluator_keys(quality_evaluations, evaluator_keys)
        selected_articles = self._select_articles(article_ids)
        if offset:
            selected_articles = selected_articles[offset:]
        if limit is not None:
            selected_articles = selected_articles[:limit]

        stored = {
            (evaluation.article_id, evaluation.evaluator): evaluation
            for evaluation in quality_evaluations
            if evaluation.evaluator in selected_keys
        }
        extractions = {item.id: item for item in self.extractions.list()}
        article_comparisons = [
            self._article_comparison(article, selected_keys, stored, extractions)
            for article in selected_articles
        ]
        aggregates = [
            self._aggregate(evaluator, article_comparisons)
            for evaluator in selected_keys
        ]
        present = sum(item.evaluated for item in aggregates)
        expected = len(selected_articles) * len(selected_keys)
        return SummaryQualityComparisonReport(
            evaluator_keys=selected_keys,
            articles_selected=len(selected_articles),
            expected_evaluations=expected,
            present=present,
            missing=expected - present,
            aggregates=aggregates,
            articles=article_comparisons,
        )

    def _select_evaluator_keys(
        self,
        evaluations: list[Evaluation],
        evaluator_keys: Iterable[str] | None,
    ) -> list[str]:
        if evaluator_keys is None:
            keys = sorted({item.evaluator for item in evaluations})
        else:
            keys = list(evaluator_keys)
            duplicates = sorted({key for key in keys if keys.count(key) > 1})
            if duplicates:
                duplicate_text = ", ".join(duplicates)
                raise ValueError(
                    f"Duplicate evaluator keys cannot be compared: {duplicate_text}"
                )
        if len(keys) < 2:
            raise ValueError(
                "Summary-quality comparison requires at least two evaluator keys. "
                "Run keyed summary-quality evaluators or repeat --evaluator."
            )
        return keys

    def _select_articles(self, article_ids: Iterable[UUID] | None) -> list[Article]:
        articles = self.articles.list()
        if article_ids is None:
            return articles
        requested = set(article_ids)
        selected = [article for article in articles if article.id in requested]
        missing = requested - {article.id for article in selected}
        if missing:
            missing_text = ", ".join(str(article_id) for article_id in sorted(missing))
            raise ValueError(
                f"Article not found for summary-quality comparison: {missing_text}"
            )
        return selected

    def _article_comparison(
        self,
        article: Article,
        evaluator_keys: list[str],
        stored: dict[tuple[UUID, str], Evaluation],
        extractions: dict[UUID, Extraction],
    ) -> ArticleSummaryQualityComparison:
        results = [
            self._result(
                evaluator,
                stored.get((article.id, evaluator)),
                extractions,
            )
            for evaluator in evaluator_keys
        ]
        return ArticleSummaryQualityComparison(
            article_id=article.id,
            article_title=article.title,
            article_source=article.source,
            results=results,
        )

    def _result(
        self,
        evaluator: str,
        evaluation: Evaluation | None,
        extractions: dict[UUID, Extraction],
    ) -> SummaryQualityComparisonResult:
        if evaluation is None:
            return SummaryQualityComparisonResult(
                evaluator=evaluator,
                status="missing",
            )
        metadata = evaluation.payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        extraction = self._summary_extraction(evaluation, extractions)
        return SummaryQualityComparisonResult(
            evaluator=evaluator,
            status="present",
            evaluation_id=evaluation.id,
            score=evaluation.score,
            confidence=evaluation.confidence,
            dimensions=self._dimensions(evaluation.payload.get("dimensions")),
            issues=self._issues(evaluation.payload.get("issues")),
            summary_extractor=self._text(evaluation.payload.get("summary_extractor")),
            summary_provider=self._payload_text(extraction, "provider"),
            summary_model=self._payload_text(extraction, "model"),
            evaluator_provider=self._text(metadata.get("provider")),
            evaluator_model=self._text(metadata.get("model")),
        )

    def _aggregate(
        self,
        evaluator: str,
        articles: list[ArticleSummaryQualityComparison],
    ) -> SummaryQualityAggregate:
        results = [
            result
            for article in articles
            for result in article.results
            if result.evaluator == evaluator and result.status == "present"
        ]
        return SummaryQualityAggregate(
            evaluator=evaluator,
            articles=len(articles),
            evaluated=len(results),
            missing=len(articles) - len(results),
            average_score=self._average(item.score for item in results),
            average_confidence=self._average(item.confidence for item in results),
            average_dimensions=SummaryQualityScores(
                **{
                    dimension: self._average(
                        getattr(item.dimensions, dimension) for item in results
                    )
                    for dimension in SUMMARY_QUALITY_DIMENSIONS
                }
            ),
            issue_count=sum(len(item.issues) for item in results),
            summary_providers=sorted(
                {
                    item.summary_provider
                    for item in results
                    if item.summary_provider is not None
                }
            ),
            summary_models=sorted(
                {
                    item.summary_model
                    for item in results
                    if item.summary_model is not None
                }
            ),
            evaluator_providers=sorted(
                {
                    item.evaluator_provider
                    for item in results
                    if item.evaluator_provider is not None
                }
            ),
            evaluator_models=sorted(
                {
                    item.evaluator_model
                    for item in results
                    if item.evaluator_model is not None
                }
            ),
        )

    def _summary_extraction(
        self,
        evaluation: Evaluation,
        extractions: dict[UUID, Extraction],
    ) -> Extraction | None:
        extraction_id = evaluation.payload.get("summary_extraction_id")
        if not isinstance(extraction_id, str):
            return None
        try:
            return extractions.get(UUID(extraction_id))
        except ValueError:
            return None

    def _payload_text(self, extraction: Extraction | None, key: str) -> str | None:
        if extraction is None:
            return None
        value = extraction.payload.get(key)
        if value is None:
            metadata = extraction.payload.get("metadata")
            if isinstance(metadata, dict):
                value = metadata.get(key)
        return self._text(value)

    def _dimensions(self, value: object) -> SummaryQualityScores:
        if not isinstance(value, dict):
            return SummaryQualityScores()
        return SummaryQualityScores(
            **{
                dimension: self._number(value.get(dimension))
                for dimension in SUMMARY_QUALITY_DIMENSIONS
            }
        )

    def _issues(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str) and item]

    def _average(self, values: Iterable[float | None]) -> float | None:
        available = [value for value in values if value is not None]
        if not available:
            return None
        return round(sum(available) / len(available), 2)

    def _number(self, value: object) -> float | None:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return None

    def _text(self, value: object) -> str | None:
        return value if isinstance(value, str) and value else None
