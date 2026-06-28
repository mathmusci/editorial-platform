from __future__ import annotations
from typing import Iterable, Protocol
from editorial.models import Article, Evaluation, Extraction, Issue, Publication

class Provider(Protocol):
    name: str
    version: str
    def fetch(self) -> Iterable[Article]: ...
class Extractor(Protocol):
    name: str
    version: str
    def extract(self, article: Article) -> Extraction: ...
class Evaluator(Protocol):
    name: str
    version: str
    def evaluate(self, article: Article) -> Evaluation: ...
class Optimiser(Protocol):
    name: str
    version: str
    def optimise(self, articles: Iterable[Article], evaluations: Iterable[Evaluation]) -> Issue: ...
class Publisher(Protocol):
    name: str
    version: str
    def publish(self, issue: Issue) -> Publication: ...
