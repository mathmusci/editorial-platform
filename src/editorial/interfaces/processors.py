from __future__ import annotations
from pathlib import Path
from typing import Iterable, Protocol
from editorial.models import (
    Article,
    Evaluation,
    Extraction,
    IssueProposal,
    OptimisationRequest,
    Publication,
)


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
        self,
        articles: list[Article],
        extractions: list[Extraction],
        evaluations: list[Evaluation],
    ) -> IssueProposal: ...

    def execute(
        self,
        request: OptimisationRequest,
        articles: list[Article],
        extractions: list[Extraction],
        evaluations: list[Evaluation],
    ) -> IssueProposal: ...


class Publisher(Processor, Protocol):
    def publish(self, publication: Publication, output_path: Path) -> None: ...
