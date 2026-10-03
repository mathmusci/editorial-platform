from __future__ import annotations

from editorial.models import Article, Extraction


def with_full_text(article: Article, extractions: list[Extraction]) -> Article:
    full_texts = [
        item
        for item in extractions
        if item.kind == "full_text"
        and isinstance(item.payload.get("content"), str)
        and item.payload["content"].strip()
    ]
    if not full_texts:
        return article
    latest = max(full_texts, key=lambda item: item.created_at)
    return article.model_copy(update={"content": latest.payload["content"]})
