# Analyse arXiv Paper Text

arXiv RSS entries usually supply an abstract rather than the paper body. Add the
`arxiv_full_text` extractor to retrieve paper text for articles already in the
database or newly ingested ones:

```yaml
providers:
  - type: rss
    url: https://rss.arxiv.org/rss/stat
    source: arXiv Statistics
extractors:
  - type: arxiv_full_text
  - type: reading_time
    words_per_minute: 200
  - type: llm_summary
    provider:
      type: ollama
      model: qwen3.5:9b
```

The full-text extractor accepts arxiv.org article links, tries arXiv HTML first,
and falls back to the PDF when HTML is unavailable or unusable. It stores the
plain text, source URL, and format as an Extraction. It skips other sources.
Reading-time and summary extractors use that text automatically, regardless of
their order in the configuration. Evaluators and the optimiser also use the stored
text when available. The original Article and abstract remain unchanged.

Start with a small run in **Operations**, for example Limit `10` and Missing only.
Download requests are sequential and spaced by at least three seconds. PDF text
quality varies; image-only PDFs without a text layer cannot be analysed and the
extraction fails clearly. Each document is limited to 40 MB.

If articles were processed before full-text retrieval was configured, their
existing summaries, reading times, and evaluations still reflect the abstract.
After obtaining full text, rerun those operations with **Replace existing** for
the selected articles. Existing proposals remain historical records; run
optimisation again to make a new proposal from the updated evidence.

The entire extracted text is passed to LLM prompts. A local model may still have
a shorter context window than the paper; in that case it may not consider every
part of the supplied text. Use a model and context setting suitable for the paper
length before treating the LLM result as a full-paper assessment.

arXiv's [API terms](https://info.arxiv.org/help/api/tou.html) permit personal and
research use of e-print content, set request limits for legacy APIs, and restrict
redistribution of full papers without appropriate permission. Keep stored paper
text within an appropriate local research workflow.
