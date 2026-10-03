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

The RSS provider stores each feed entry as an Article with its title, abstract,
and arXiv URL. The `source` label names the feed; it does not determine whether
full-text extraction runs. The extractor recognises arxiv.org article URLs,
tries arXiv HTML first, and falls back to the PDF when HTML is unavailable or
unusable. It stores the plain text, source URL, format, and word count in a
separate `full_text` Extraction. It skips non-arXiv articles.

Full-text retrieval runs before the other extractors even if it appears later
in the configuration. Reading-time and summary extractors use the stored paper
text. Evaluators and the optimiser also use it when available. The original
Article and abstract remain unchanged. If retrieval fails, the full-text
operation fails, but other extractors may still process the title and abstract.

`reading_time` counts the title, abstract, and paper text, then rounds up using
`words_per_minute` (200 in this example). Its word count may therefore be higher
than the full-text Extraction's paper-only word count. The reading-time estimate
is not strictly for the paper body alone. Without a summary extractor or
evaluator in the configuration, this example produces neither summaries nor
evaluations.

Start with a small run in **Operations**, for example Limit `10` and Missing only.
Download requests are sequential and spaced by at least three seconds. PDF text
quality varies; image-only PDFs without a text layer cannot be analysed and the
extraction fails clearly. Each document is limited to 40 MB.

For newly ingested articles, one extraction run processes both configured
extractors. If articles were processed before full-text retrieval was configured,
their existing summaries, reading times, and evaluations still reflect the
abstract. Run extraction with **Missing only** to fetch missing paper text, then
run it again with **Replace existing** to recalculate reading time and any
configured summaries. Rerun evaluation with **Replace existing** if evaluators
were previously run. On the CLI, these options are `--missing-only` and
`--force` respectively; they cannot be combined in one run. Existing proposals
remain historical records; run optimisation again to make a new proposal from
the updated evidence.

The entire extracted text is passed to LLM prompts. A local model may still have
a shorter context window than the paper; in that case it may not consider every
part of the supplied text. Use a model and context setting suitable for the paper
length before treating the LLM result as a full-paper assessment.

arXiv's [API terms](https://info.arxiv.org/help/api/tou.html) permit personal and
research use of e-print content, set request limits for legacy APIs, and restrict
redistribution of full papers without appropriate permission. Keep stored paper
text within an appropriate local research workflow.
