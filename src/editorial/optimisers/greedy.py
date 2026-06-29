from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from editorial.models import (
    Article,
    ConstraintResult,
    Evaluation,
    Extraction,
    IssueProposal,
)


@dataclass(frozen=True)
class Candidate:
    article: Article
    relevance_score: float
    reading_minutes: float
    mandatory_terms: set[str]


class GreedyOptimiser:
    name = "greedy"
    version = "0.1.0"

    def __init__(
        self,
        max_articles: int = 8,
        minimum_relevance_score: float = 0,
        reading_time_target_minutes: float | None = None,
        reading_time_weight: float = 3,
        mandatory_terms: list[str] | None = None,
        mandatory_terms_weight: float = 5,
        source_diversity_max_per_source: int | None = None,
        source_diversity_weight: float = 2,
    ):
        self.max_articles = max_articles
        self.minimum_relevance_score = minimum_relevance_score
        self.reading_time_target_minutes = reading_time_target_minutes
        self.reading_time_weight = reading_time_weight
        self.mandatory_terms = [term.lower() for term in mandatory_terms or []]
        self.mandatory_terms_weight = mandatory_terms_weight
        self.source_diversity_max_per_source = source_diversity_max_per_source
        self.source_diversity_weight = source_diversity_weight

    def optimise(
        self,
        articles: list[Article],
        extractions: list[Extraction],
        evaluations: list[Evaluation],
    ) -> IssueProposal:
        extraction_by_article = self._extractions_by_article(extractions)
        latest_relevance = self._latest_relevance_by_article(evaluations)
        candidates = [
            self._candidate(
                article,
                extraction_by_article.get(article.id, []),
                latest_relevance[article.id],
            )
            for article in articles
            if article.id in latest_relevance
            and latest_relevance[article.id].score is not None
            if latest_relevance[article.id].score >= self.minimum_relevance_score
        ]
        candidates.sort(
            key=lambda candidate: (
                -candidate.relevance_score,
                article_sort_key(candidate.article),
            )
        )

        selected: list[Candidate] = []
        current_value = self._objective(selected)
        remaining = list(candidates)
        while len(selected) < self.max_articles and remaining:
            best_candidate: Candidate | None = None
            best_value = current_value
            best_index = -1
            for index, candidate in enumerate(remaining):
                proposal_value = self._objective([*selected, candidate])
                if proposal_value > best_value:
                    best_candidate = candidate
                    best_value = proposal_value
                    best_index = index
            if best_candidate is None:
                break
            selected.append(best_candidate)
            remaining.pop(best_index)
            current_value = best_value

        return IssueProposal(
            optimiser=self.name,
            optimiser_version=self.version,
            article_ids=[candidate.article.id for candidate in selected],
            objective_value=round(current_value, 2),
            constraint_results=self._constraint_results(selected),
            metadata={
                "strategy": self.name,
                "candidate_count": len(candidates),
                "selected": [
                    {
                        "article_id": str(candidate.article.id),
                        "relevance_score": candidate.relevance_score,
                        "reading_minutes": candidate.reading_minutes,
                        "mandatory_terms": sorted(candidate.mandatory_terms),
                        "source": candidate.article.source,
                    }
                    for candidate in selected
                ],
            },
        )

    def _candidate(
        self,
        article: Article,
        extractions: list[Extraction],
        evaluation: Evaluation,
    ) -> Candidate:
        return Candidate(
            article=article,
            relevance_score=float(evaluation.score or 0),
            reading_minutes=self._reading_minutes(extractions),
            mandatory_terms=self._mandatory_terms_for_article(article),
        )

    def _objective(self, selected: list[Candidate]) -> float:
        relevance = sum(candidate.relevance_score for candidate in selected)
        mandatory_reward = (
            len(self._covered_mandatory_terms(selected)) * self.mandatory_terms_weight
        )
        reading_penalty = self._reading_time_penalty(selected)
        source_penalty = self._source_diversity_penalty(selected)
        return relevance + mandatory_reward - reading_penalty - source_penalty

    def _constraint_results(self, selected: list[Candidate]) -> list[ConstraintResult]:
        total_reading_minutes = self._total_reading_minutes(selected)
        relevance_scores = [candidate.relevance_score for candidate in selected]
        covered_terms = sorted(self._covered_mandatory_terms(selected))
        source_counts = dict(self._source_counts(selected))
        results = [
            ConstraintResult(
                name="max_articles",
                kind="hard",
                satisfied=len(selected) <= self.max_articles,
                value=len(selected),
                target=self.max_articles,
                penalty=0,
            ),
            ConstraintResult(
                name="minimum_relevance_score",
                kind="hard",
                satisfied=all(
                    score >= self.minimum_relevance_score for score in relevance_scores
                ),
                value=min(relevance_scores) if relevance_scores else None,
                target=self.minimum_relevance_score,
                penalty=0,
            ),
        ]
        if self.reading_time_target_minutes is not None:
            deviation = abs(total_reading_minutes - self.reading_time_target_minutes)
            results.append(
                ConstraintResult(
                    name="reading_time_target_minutes",
                    kind="goal",
                    satisfied=deviation == 0,
                    value=total_reading_minutes,
                    target=self.reading_time_target_minutes,
                    penalty=round(deviation * self.reading_time_weight, 2),
                    message="Target is a soft goal; deviation creates a penalty.",
                )
            )
        if self.mandatory_terms:
            missing_terms = sorted(set(self.mandatory_terms) - set(covered_terms))
            results.append(
                ConstraintResult(
                    name="mandatory_terms",
                    kind="soft",
                    satisfied=not missing_terms,
                    value=covered_terms,
                    target=self.mandatory_terms,
                    penalty=len(missing_terms) * self.mandatory_terms_weight,
                    message=f"Missing terms: {missing_terms}"
                    if missing_terms
                    else None,
                )
            )
        if self.source_diversity_max_per_source is not None:
            overage = sum(
                max(0, count - self.source_diversity_max_per_source)
                for count in source_counts.values()
            )
            results.append(
                ConstraintResult(
                    name="source_diversity_max_per_source",
                    kind="soft",
                    satisfied=overage == 0,
                    value=source_counts,
                    target=self.source_diversity_max_per_source,
                    penalty=overage * self.source_diversity_weight,
                )
            )
        return results

    def _latest_relevance_by_article(
        self, evaluations: list[Evaluation]
    ) -> dict[UUID, Evaluation]:
        latest: dict[UUID, Evaluation] = {}
        for evaluation in sorted(evaluations, key=lambda item: item.created_at):
            if evaluation.kind == "relevance" and evaluation.score is not None:
                latest[evaluation.article_id] = evaluation
        return latest

    def _extractions_by_article(
        self, extractions: list[Extraction]
    ) -> dict[UUID, list[Extraction]]:
        grouped: dict[UUID, list[Extraction]] = {}
        for extraction in extractions:
            grouped.setdefault(extraction.article_id, []).append(extraction)
        return grouped

    def _reading_minutes(self, extractions: list[Extraction]) -> float:
        reading_time_extractions = [
            extraction
            for extraction in extractions
            if extraction.kind == "reading_time"
        ]
        if not reading_time_extractions:
            return 0
        payload = sorted(reading_time_extractions, key=lambda item: item.created_at)[
            -1
        ].payload
        value = (
            payload.get("reading_minutes")
            or payload.get("reading_time_minutes")
            or payload.get("minutes")
            or 0
        )
        return float(value)

    def _mandatory_terms_for_article(self, article: Article) -> set[str]:
        text = " ".join(
            part.lower()
            for part in [article.title, article.summary, article.content]
            if part
        )
        return {term for term in self.mandatory_terms if term in text}

    def _covered_mandatory_terms(self, selected: list[Candidate]) -> set[str]:
        return {term for candidate in selected for term in candidate.mandatory_terms}

    def _total_reading_minutes(self, selected: list[Candidate]) -> float:
        return sum(candidate.reading_minutes for candidate in selected)

    def _reading_time_penalty(self, selected: list[Candidate]) -> float:
        if self.reading_time_target_minutes is None:
            return 0
        return (
            abs(
                self._total_reading_minutes(selected) - self.reading_time_target_minutes
            )
            * self.reading_time_weight
        )

    def _source_counts(self, selected: list[Candidate]) -> Counter[str]:
        return Counter(candidate.article.source or "" for candidate in selected)

    def _source_diversity_penalty(self, selected: list[Candidate]) -> float:
        if self.source_diversity_max_per_source is None:
            return 0
        return sum(
            max(0, count - self.source_diversity_max_per_source)
            * self.source_diversity_weight
            for count in self._source_counts(selected).values()
        )


def article_sort_key(article: Article) -> tuple[str, str]:
    return (str(article.url) if article.url else "", str(article.id))
