from __future__ import annotations

import re
from math import isfinite
from typing import Iterable, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from editorial.inspection.evaluation_comparison import (
    SUMMARY_QUALITY_DIMENSIONS,
    SummaryQualityScores,
)
from editorial.models import Article, Evaluation
from editorial.storage import (
    SQLiteArticleRepository,
    SQLiteEvaluationRepository,
    SQLiteExtractionRepository,
)


EVALUATOR_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class SummaryQualityCalibrationResult(BaseModel):
    article_id: UUID
    article_title: str
    summary_extraction_id: UUID
    status: Literal[
        "matched",
        "missing_candidate",
        "different_summary",
        "unverifiable_summary",
    ]
    reference_evaluation_id: UUID
    candidate_evaluation_id: UUID | None = None
    reference_score: float | None = None
    candidate_score: float | None = None
    score_delta: float | None = None
    dimension_deltas: SummaryQualityScores = Field(default_factory=SummaryQualityScores)
    candidate_provider: str | None = None
    candidate_model: str | None = None


class SummaryQualityCalibrationMetrics(BaseModel):
    mean_absolute_error: float | None = None
    mean_error: float | None = None
    within_tolerance: int = 0
    compared_scores: int = 0
    within_tolerance_percentage: float | None = None
    dimension_mean_absolute_error: SummaryQualityScores = Field(
        default_factory=SummaryQualityScores
    )


class SummaryQualityCalibrationReport(BaseModel):
    reference_evaluator: str
    candidate_evaluator: str
    tolerance: float
    references_selected: int
    matched: int
    missing_candidate: int
    different_summary: int
    unverifiable_summary: int
    candidate_providers: list[str] = Field(default_factory=list)
    candidate_models: list[str] = Field(default_factory=list)
    metrics: SummaryQualityCalibrationMetrics
    articles: list[SummaryQualityCalibrationResult]


class HumanSummaryQualityReferenceService:
    version = "human-v1"

    def __init__(
        self,
        evaluations: SQLiteEvaluationRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
    ):
        self.evaluations = evaluations
        self.articles = articles
        self.extractions = extractions

    def record(
        self,
        *,
        article_id: UUID,
        summary_extraction_id: UUID,
        evaluator: str,
        reviewer: str,
        faithfulness: float,
        coverage: float,
        clarity: float,
        concision: float,
        rationale: str,
        confidence: float | None = None,
        evidence: Iterable[str] = (),
        issues: Iterable[str] = (),
    ) -> Evaluation:
        article = self.articles.get(article_id)
        if article is None:
            raise ValueError(f"Article not found: {article_id}")
        extraction = self.extractions.get(summary_extraction_id)
        if extraction is None:
            raise ValueError(f"Summary extraction not found: {summary_extraction_id}")
        if extraction.article_id != article_id:
            raise ValueError(
                f"Extraction {summary_extraction_id} does not belong to article "
                f"{article_id}"
            )
        if extraction.kind != "summary":
            raise ValueError(
                f"Extraction {summary_extraction_id} is {extraction.kind!r}, not a "
                "summary"
            )
        self._validate_key(evaluator)
        reviewer = self._required_text(reviewer, "Reviewer")
        rationale = self._required_text(rationale, "Rationale")
        dimensions = {
            "faithfulness": self._score(faithfulness, "Faithfulness"),
            "coverage": self._score(coverage, "Coverage"),
            "clarity": self._score(clarity, "Clarity"),
            "concision": self._score(concision, "Concision"),
        }
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        evidence_items = self._text_items(evidence, "Evidence")
        issue_items = self._text_items(issues, "Issue")
        evaluation = Evaluation(
            article_id=article_id,
            evaluator=evaluator,
            evaluator_version=self.version,
            kind="summary_quality",
            criterion="summary_quality",
            score=round(sum(dimensions.values()) / len(dimensions), 2),
            confidence=confidence,
            rationale=rationale,
            payload={
                "dimensions": dimensions,
                "evidence": evidence_items,
                "issues": issue_items,
                "summary_extraction_id": str(extraction.id),
                "summary_extractor": extraction.extractor,
                "metadata": {
                    "generated_by": "human",
                    "reviewer": reviewer,
                },
            },
        )
        self.evaluations.insert(evaluation)
        return evaluation

    def _validate_key(self, evaluator: str) -> None:
        if not EVALUATOR_KEY_PATTERN.fullmatch(evaluator):
            raise ValueError(
                "Evaluator key must start with a letter or number and contain only "
                "letters, numbers, underscores, and hyphens"
            )

    def _score(self, value: float, label: str) -> float:
        if not 0 <= value <= 100:
            raise ValueError(f"{label} must be between 0 and 100")
        return float(value)

    def _required_text(self, value: str, label: str) -> str:
        if not value.strip():
            raise ValueError(f"{label} must not be empty")
        return value.strip()

    def _text_items(self, values: Iterable[str], label: str) -> list[str]:
        items = [value.strip() for value in values]
        if any(not item for item in items):
            raise ValueError(f"{label} values must not be empty")
        return items


class SummaryQualityCalibrationService:
    def __init__(
        self,
        evaluations: SQLiteEvaluationRepository,
        articles: SQLiteArticleRepository,
        extractions: SQLiteExtractionRepository,
    ):
        self.evaluations = evaluations
        self.articles = articles
        self.extractions = extractions

    def calibrate(
        self,
        *,
        reference_evaluator: str,
        candidate_evaluator: str,
        tolerance: float = 10,
        article_ids: Iterable[UUID] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> SummaryQualityCalibrationReport:
        if reference_evaluator == candidate_evaluator:
            raise ValueError("Reference and candidate evaluator keys must differ")
        if not isfinite(tolerance) or not 0 <= tolerance <= 100:
            raise ValueError("Calibration tolerance must be between 0 and 100")
        if limit is not None and limit <= 0:
            raise ValueError("Calibration limit must be a positive integer")
        if offset < 0:
            raise ValueError("Calibration offset must be zero or greater")

        evaluations = [
            item for item in self.evaluations.list() if item.kind == "summary_quality"
        ]
        references = {
            item.article_id: item
            for item in evaluations
            if item.evaluator == reference_evaluator
        }
        if not references:
            raise ValueError(
                f"No summary-quality references found for {reference_evaluator!r}"
            )
        non_human = [
            item
            for item in references.values()
            if self._metadata_text(item, "generated_by") != "human"
        ]
        if non_human:
            raise ValueError(
                f"Reference evaluator {reference_evaluator!r} contains evaluations "
                "that are not recorded as human judgements"
            )

        candidates = {
            item.article_id: item
            for item in evaluations
            if item.evaluator == candidate_evaluator
        }
        articles = self._select_reference_articles(references, article_ids)
        if offset:
            articles = articles[offset:]
        if limit is not None:
            articles = articles[:limit]
        results = [
            self._result(article, references[article.id], candidates.get(article.id))
            for article in articles
        ]
        matched = [item for item in results if item.status == "matched"]
        return SummaryQualityCalibrationReport(
            reference_evaluator=reference_evaluator,
            candidate_evaluator=candidate_evaluator,
            tolerance=float(tolerance),
            references_selected=len(results),
            matched=len(matched),
            missing_candidate=sum(
                item.status == "missing_candidate" for item in results
            ),
            different_summary=sum(
                item.status == "different_summary" for item in results
            ),
            unverifiable_summary=sum(
                item.status == "unverifiable_summary" for item in results
            ),
            candidate_providers=sorted(
                {
                    item.candidate_provider
                    for item in matched
                    if item.candidate_provider is not None
                }
            ),
            candidate_models=sorted(
                {
                    item.candidate_model
                    for item in matched
                    if item.candidate_model is not None
                }
            ),
            metrics=self._metrics(matched, tolerance),
            articles=results,
        )

    def _select_reference_articles(
        self,
        references: dict[UUID, Evaluation],
        article_ids: Iterable[UUID] | None,
    ) -> list[Article]:
        articles = [
            article for article in self.articles.list() if article.id in references
        ]
        missing_articles = set(references) - {article.id for article in articles}
        if missing_articles:
            missing_text = ", ".join(
                str(article_id) for article_id in sorted(missing_articles)
            )
            raise ValueError(f"Referenced article not found: {missing_text}")
        if article_ids is None:
            return articles
        requested = set(article_ids)
        selected = [article for article in articles if article.id in requested]
        missing_references = requested - {article.id for article in selected}
        if missing_references:
            missing_text = ", ".join(
                str(article_id) for article_id in sorted(missing_references)
            )
            raise ValueError(
                f"Human summary-quality reference not found: {missing_text}"
            )
        return selected

    def _result(
        self,
        article: Article,
        reference: Evaluation,
        candidate: Evaluation | None,
    ) -> SummaryQualityCalibrationResult:
        reference_extraction_id = self._summary_extraction_id(reference)
        if reference_extraction_id is None:
            raise ValueError(
                f"Human reference {reference.id} has no valid summary extraction ID"
            )
        reference_extraction = self.extractions.get(reference_extraction_id)
        if reference_extraction is None:
            raise ValueError(
                f"Summary extraction linked by human reference {reference.id} "
                f"was not found: {reference_extraction_id}"
            )
        if reference_extraction.article_id != article.id:
            raise ValueError(
                f"Summary extraction {reference_extraction_id} linked by human "
                f"reference {reference.id} does not belong to article {article.id}"
            )
        if reference_extraction.kind != "summary":
            raise ValueError(
                f"Extraction {reference_extraction_id} linked by human reference "
                f"{reference.id} is not a summary"
            )
        if candidate is None:
            return SummaryQualityCalibrationResult(
                article_id=article.id,
                article_title=article.title,
                summary_extraction_id=reference_extraction_id,
                status="missing_candidate",
                reference_evaluation_id=reference.id,
                reference_score=reference.score,
            )

        candidate_extraction_id = self._summary_extraction_id(candidate)
        if candidate_extraction_id is None:
            status = "unverifiable_summary"
        elif candidate_extraction_id != reference_extraction_id:
            status = "different_summary"
        else:
            status = "matched"
        score_delta = (
            self._delta(candidate.score, reference.score)
            if status == "matched"
            else None
        )
        reference_dimensions = self._dimensions(reference)
        candidate_dimensions = self._dimensions(candidate)
        metadata = candidate.payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return SummaryQualityCalibrationResult(
            article_id=article.id,
            article_title=article.title,
            summary_extraction_id=reference_extraction_id,
            status=status,
            reference_evaluation_id=reference.id,
            candidate_evaluation_id=candidate.id,
            reference_score=reference.score,
            candidate_score=candidate.score,
            score_delta=score_delta,
            dimension_deltas=SummaryQualityScores(
                **{
                    dimension: self._delta(
                        getattr(candidate_dimensions, dimension),
                        getattr(reference_dimensions, dimension),
                    )
                    if status == "matched"
                    else None
                    for dimension in SUMMARY_QUALITY_DIMENSIONS
                }
            ),
            candidate_provider=self._text(metadata.get("provider")),
            candidate_model=self._text(metadata.get("model")),
        )

    def _metrics(
        self,
        matched: list[SummaryQualityCalibrationResult],
        tolerance: float,
    ) -> SummaryQualityCalibrationMetrics:
        deltas = [item.score_delta for item in matched if item.score_delta is not None]
        within = sum(abs(delta) <= tolerance for delta in deltas)
        return SummaryQualityCalibrationMetrics(
            mean_absolute_error=self._mean(abs(delta) for delta in deltas),
            mean_error=self._mean(deltas),
            within_tolerance=within,
            compared_scores=len(deltas),
            within_tolerance_percentage=(
                round(within / len(deltas) * 100, 2) if deltas else None
            ),
            dimension_mean_absolute_error=SummaryQualityScores(
                **{
                    dimension: self._mean(
                        abs(delta)
                        for item in matched
                        if (delta := getattr(item.dimension_deltas, dimension))
                        is not None
                    )
                    for dimension in SUMMARY_QUALITY_DIMENSIONS
                }
            ),
        )

    def _summary_extraction_id(self, evaluation: Evaluation) -> UUID | None:
        value = evaluation.payload.get("summary_extraction_id")
        if not isinstance(value, str):
            return None
        try:
            return UUID(value)
        except ValueError:
            return None

    def _dimensions(self, evaluation: Evaluation) -> SummaryQualityScores:
        dimensions = evaluation.payload.get("dimensions")
        if not isinstance(dimensions, dict):
            return SummaryQualityScores()
        return SummaryQualityScores(
            **{
                dimension: self._number(dimensions.get(dimension))
                for dimension in SUMMARY_QUALITY_DIMENSIONS
            }
        )

    def _delta(
        self,
        candidate: float | None,
        reference: float | None,
    ) -> float | None:
        if candidate is None or reference is None:
            return None
        return round(candidate - reference, 2)

    def _mean(self, values: Iterable[float]) -> float | None:
        available = list(values)
        if not available:
            return None
        return round(sum(available) / len(available), 2)

    def _metadata_text(self, evaluation: Evaluation, key: str) -> str | None:
        metadata = evaluation.payload.get("metadata")
        if not isinstance(metadata, dict):
            return None
        return self._text(metadata.get(key))

    def _number(self, value: object) -> float | None:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return None

    def _text(self, value: object) -> str | None:
        return value if isinstance(value, str) and value else None
