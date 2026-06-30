from __future__ import annotations

from editorial.llm import LLMProvider
from editorial.models import Article, Extraction
from editorial.prompts import SUMMARY_PROMPT_VERSION, build_summary_prompt


class LLMSummaryExtractor:
    name = "llm_summary"
    version = "0.1.0"

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract(self, article: Article) -> Extraction:
        prompt = build_summary_prompt(article)
        response = self.provider.generate(prompt)
        return Extraction(
            article_id=article.id,
            extractor=self.name,
            extractor_version=self.version,
            kind="summary",
            payload={
                "summary": response.content,
                "metadata": {
                    "generated_by": "llm",
                    "provider": self.provider.name,
                    "model": response.model,
                    "prompt_version": SUMMARY_PROMPT_VERSION,
                },
            },
        )
