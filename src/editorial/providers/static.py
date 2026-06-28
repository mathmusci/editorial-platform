from __future__ import annotations
from typing import Iterable
from editorial.models import Article
class StaticProvider:
    name = "static"
    version = "0.1.0"
    def __init__(self, articles: list[dict]):
        self._articles = articles
    def fetch(self) -> Iterable[Article]:
        for item in self._articles:
            yield Article.model_validate(item)
