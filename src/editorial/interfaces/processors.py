from __future__ import annotations
from typing import Iterable, Protocol
from editorial.models import Article, Evaluation, Extraction, Issue, Publication


class Processor(Protocol):
    name: str
    version: str


class Provider(Processor, Protocol):
    def fetch(self) -> Iterable[Article]: ...


class Extractor(Processor, Protocol):
    def extract(self, article: Article) -> Extraction: ...


class Evaluator(Processor, Protocol):
    def evaluate(
        self, article: Article, extractions: list[Extraction]
    ) -> Evaluation: ...


class Optimiser(Processor, Protocol):
    def optimise(
        self, articles: Iterable[Article], evaluations: Iterable[Evaluation]
    ) -> Issue: ...


class Publisher(Processor, Protocol):
    def publish(self, issue: Issue) -> Publication: ...
