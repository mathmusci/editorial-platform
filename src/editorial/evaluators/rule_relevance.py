from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from editorial.models import Article, Evaluation, Extraction


class RuleBasedRelevanceEvaluator:
    name = "rule_relevance"
    version = "0.1.0"

    def __init__(
        self,
        include: Sequence[str],
        exclude: Sequence[str],
        weights: Mapping[str, int | float] | None = None,
    ):
        self.include = [term.lower() for term in include]
        self.exclude = [term.lower() for term in exclude]
        configured_weights = dict(weights or {})
        self.weights = {
            "title": float(configured_weights.get("title", 5)),
            "summary": float(configured_weights.get("summary", 2)),
            "content": float(configured_weights.get("content", 1)),
        }

    def evaluate(self, article: Article, extractions: list[Extraction]) -> Evaluation:
        fields = {
            "title": article.title,
            "summary": article.summary or "",
            "content": article.content or "",
        }
        include_matches, include_score = self._score_terms(fields, self.include)
        exclude_matches, exclude_score = self._score_terms(fields, self.exclude)
        maximum_include_score = max(len(self.include) * sum(self.weights.values()), 1)
        score = max(
            0.0,
            min(100.0, ((include_score - exclude_score) / maximum_include_score) * 100),
        )

        return Evaluation(
            article_id=article.id,
            evaluator=self.name,
            evaluator_version=self.version,
            kind="relevance",
            criterion="relevance",
            score=round(score, 2),
            confidence=1.0,
            rationale=self._rationale(include_matches, exclude_matches),
            payload={
                "matched_include_terms": self._matched_terms(include_matches),
                "matched_exclude_terms": self._matched_terms(exclude_matches),
                "scoring": {
                    "include_score": include_score,
                    "exclude_score": exclude_score,
                    "maximum_include_score": maximum_include_score,
                    "weights": self.weights,
                },
                "extractions": [
                    {"kind": extraction.kind, "extractor": extraction.extractor}
                    for extraction in extractions
                ],
            },
        )

    def _score_terms(
        self, fields: Mapping[str, str], terms: Sequence[str]
    ) -> tuple[dict[str, list[str]], float]:
        matches: dict[str, list[str]] = {}
        score = 0.0
        for field, text in fields.items():
            field_matches = [term for term in terms if self._contains_term(text, term)]
            matches[field] = field_matches
            score += len(field_matches) * self.weights[field]
        return matches, score

    def _contains_term(self, text: str, term: str) -> bool:
        return re.search(rf"\b{re.escape(term)}\b", text.lower()) is not None

    def _matched_terms(self, matches: Mapping[str, Sequence[str]]) -> list[str]:
        return sorted({term for terms in matches.values() for term in terms})

    def _rationale(
        self,
        include_matches: Mapping[str, Sequence[str]],
        exclude_matches: Mapping[str, Sequence[str]],
    ) -> str:
        include_terms = self._matched_terms(include_matches)
        exclude_terms = self._matched_terms(exclude_matches)
        if exclude_terms:
            return f"Matched include terms {include_terms}; excluded terms {exclude_terms}."
        return f"Matched include terms {include_terms}."
