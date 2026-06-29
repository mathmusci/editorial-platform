from __future__ import annotations

import math
import re

from editorial.models import Article, Extraction


class ReadingTimeExtractor:
    name = "reading_time"
    version = "0.1.0"

    def __init__(self, words_per_minute: int = 200):
        if words_per_minute <= 0:
            raise ValueError("words_per_minute must be greater than zero")
        self.words_per_minute = words_per_minute

    def extract(self, article: Article) -> Extraction:
        text = "\n".join(
            part for part in [article.title, article.summary, article.content] if part
        )
        word_count = len(re.findall(r"\b\w+\b", text))
        reading_minutes = (
            math.ceil(word_count / self.words_per_minute) if word_count else 0
        )
        return Extraction(
            article_id=article.id,
            extractor=self.name,
            extractor_version=self.version,
            kind="reading_time",
            payload={
                "word_count": word_count,
                "reading_minutes": reading_minutes,
                "words_per_minute": self.words_per_minute,
            },
        )
