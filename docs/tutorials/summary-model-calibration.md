# Summary Model Comparison And Human Calibration

This tutorial explains how to compare several summary models and then check
whether the automated summary-quality evaluator agrees with human editorial
judgement.

The workflow answers two different questions:

1. Which model appears to produce the strongest summaries?
2. Is the automated evaluator making judgements that an editor considers
   credible?

The second question matters because a precise comparison produced by an
uncalibrated evaluator can still be misleading.

## The three roles

Summary generation, automated evaluation and human calibration are separate
activities:

```text
Summary model
    creates a summary Extraction
        ↓
LLM summary-quality evaluator
    scores the summary automatically
        ↓
Human reference
    scores the same stored summary
        ↓
Calibration
    measures disagreement between the two Evaluations
```

The summary model creates editorial evidence. The LLM evaluator judges that
evidence. The human reference provides a small editorial benchmark against
which the evaluator can be measured.

Calibration does not train, tune or modify either model. It reads stored
artefacts and reports agreement.

## Configure a three-model experiment

Each instance needs a stable key so that its artefacts can coexist in one
database. The display `name` is for people; the `key` is the identity stored on
an Extraction or Evaluation.

The following example generates summaries with the three local models used in
the BIS experiments:

```yaml
extractors:
  - type: llm_summary
    key: summary_qwen
    name: Qwen summary
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 200

  - type: llm_summary
    key: summary_deepseek
    name: DeepSeek summary
    provider:
      type: ollama
      model: deepseek-r1:8b
      temperature: 0
      max_tokens: 200

  - type: llm_summary
    key: summary_gpt_oss
    name: GPT-OSS summary
    provider:
      type: ollama
      model: gpt-oss:20b
      temperature: 0
      max_tokens: 200
```

Configure one quality evaluator for each summary extractor. Use the same judge
model and settings for every candidate so that the summary model is the main
changing variable:

```yaml
evaluators:
  - type: llm_summary_quality
    key: quality_qwen
    name: Qwen summary quality
    summary_extractor: summary_qwen
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300

  - type: llm_summary_quality
    key: quality_deepseek
    name: DeepSeek summary quality
    summary_extractor: summary_deepseek
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300

  - type: llm_summary_quality
    key: quality_gpt_oss
    name: GPT-OSS summary quality
    summary_extractor: summary_gpt_oss
    provider:
      type: ollama
      model: qwen3.5:9b
      temperature: 0
      max_tokens: 300
```

A fixed judge improves comparability, but it does not guarantee neutrality. In
this example Qwen also judges Qwen-generated summaries, which could introduce a
self-preference. Human calibration is how that possibility becomes measurable
rather than implicit.

## Run a small experiment

Start with a deterministic subset instead of the complete corpus:

```bash
editorial extract \
  --config publication-model-comparison.yaml \
  --db model-comparison.sqlite \
  --limit 5 \
  --progress
```

Five articles and three configured summary extractors produce 15 extraction
operations. Then evaluate those summaries:

```bash
editorial evaluate \
  --config publication-model-comparison.yaml \
  --db model-comparison.sqlite \
  --limit 5 \
  --progress
```

This produces up to 15 automated summary-quality Evaluations. The runs remain
sequential. Use `--missing-only` to resume either command without repeating
completed keyed operations.

## Compare the automated results

Compare all stored summary-quality evaluator keys:

```bash
editorial evaluation compare --db model-comparison.sqlite
```

Or name the three keys explicitly:

```bash
editorial evaluation compare \
  --db model-comparison.sqlite \
  --evaluator quality_qwen \
  --evaluator quality_deepseek \
  --evaluator quality_gpt_oss
```

The aggregate view reports:

- overall quality;
- faithfulness, coverage, clarity and concision;
- evaluator confidence;
- issue counts;
- present and missing evaluation coverage; and
- separate provenance for the summary model and judge model.

The article view exposes the same information for each individual summary.
These scores describe what the automated judge thinks. They are not yet evidence
that the judge agrees with an editor.

## Build a human reference set

Choose a varied subset containing strong, weak and borderline summaries. Include
different article lengths and subject matter. A larger and more representative
set gives stronger evidence; a small set is useful for finding obvious scoring
problems early.

For one selected article, inspect its stored artefacts:

```bash
editorial article show <article-id> --db model-comparison.sqlite
editorial extraction show <summary-extraction-id> --db model-comparison.sqlite
```

The article should have three summary Extractions, for example:

```text
summary_qwen      → extraction A
summary_deepseek  → extraction B
summary_gpt_oss   → extraction C
```

Read each summary against the original article. Assign scores from 0 to 100 for:

- **Faithfulness:** Are all claims supported by the source?
- **Coverage:** Does the summary retain the important information?
- **Clarity:** Is it understandable and well structured?
- **Concision:** Is it appropriately brief without wasteful repetition?

Record the Qwen reference:

```bash
editorial evaluation record-reference <article-id> \
  --summary-extraction-id <extraction-A> \
  --evaluator human_qwen \
  --reviewer "Editor name" \
  --faithfulness 90 \
  --coverage 75 \
  --clarity 85 \
  --concision 80 \
  --confidence 0.9 \
  --rationale "Accurate and readable, but misses the regional detail." \
  --evidence "The reported increase matches the source article." \
  --issue "Regional differences are omitted." \
  --db model-comparison.sqlite
```

Record the DeepSeek reference under a different human evaluator key:

```bash
editorial evaluation record-reference <article-id> \
  --summary-extraction-id <extraction-B> \
  --evaluator human_deepseek \
  --reviewer "Editor name" \
  --faithfulness 70 \
  --coverage 90 \
  --clarity 65 \
  --concision 60 \
  --rationale "Comprehensive, but verbose and slightly overstates the result." \
  --issue "The conclusion is stronger than the source supports." \
  --db model-comparison.sqlite
```

Record the GPT-OSS reference in the same way:

```bash
editorial evaluation record-reference <article-id> \
  --summary-extraction-id <extraction-C> \
  --evaluator human_gpt_oss \
  --reviewer "Editor name" \
  --faithfulness 85 \
  --coverage 80 \
  --clarity 90 \
  --concision 90 \
  --rationale "Accurate, clear and appropriately concise." \
  --db model-comparison.sqlite
```

Repeat this for every article in the reference set. Five articles evaluated
across three summary models result in 15 human judgements.

Human references are ordinary `summary_quality` Evaluation artefacts. They
store the four dimensions, overall mean score, optional confidence, rationale,
evidence, issues, reviewer and exact summary Extraction ID. Repeating the
command for the same article and human evaluator key updates that reference.

## Calibrate each evaluator pair

Each automated evaluator must be paired with the human key for the same summary
model:

```text
human_qwen       ↔ quality_qwen
human_deepseek   ↔ quality_deepseek
human_gpt_oss    ↔ quality_gpt_oss
```

Run calibration for Qwen summaries:

```bash
editorial evaluation calibrate \
  --reference human_qwen \
  --evaluator quality_qwen \
  --tolerance 10 \
  --db model-comparison.sqlite
```

Repeat it for the other pairs:

```bash
editorial evaluation calibrate \
  --reference human_deepseek \
  --evaluator quality_deepseek \
  --tolerance 10 \
  --db model-comparison.sqlite
```

```bash
editorial evaluation calibrate \
  --reference human_gpt_oss \
  --evaluator quality_gpt_oss \
  --tolerance 10 \
  --db model-comparison.sqlite
```

`--limit`, `--offset` and repeatable `--article-id` options can restrict the
reference set. Calibration does not call an LLM or modify stored Evaluations.

## Interpret the report

A calibration report might contain:

```text
References selected: 5
Matched: 5
Missing candidate: 0
Different summary: 0
Unverifiable summary: 0

Mean absolute error: 6.40
Mean error (bias): +4.20
Within tolerance: 4/5 (80.0%)

Faithfulness MAE: 9.00
Content coverage MAE: 5.00
Clarity MAE: 4.50
Concision MAE: 7.00
```

Interpret those values as follows:

- **Mean absolute error 6.40:** automated overall scores differ from the human
  scores by 6.4 points on average, regardless of direction.
- **Mean error +4.20:** automated scores are 4.2 points higher than human scores
  on average. Error is calculated as candidate minus human, so positive values
  indicate generosity and negative values indicate severity.
- **Within tolerance 80%:** four of five automated overall scores are within ten
  points of their human references.
- **Faithfulness MAE 9.00:** faithfulness has the largest average disagreement in
  this example and deserves closer inspection.

Overall error can hide dimensions moving in opposite directions, which is why
the four dimension errors are reported separately.

## Understand lineage statuses

Calibration only measures agreement when the automated and human Evaluations
point to exactly the same summary Extraction ID.

- `matched`: both judgements concern the same summary and contribute to metrics.
- `missing candidate`: a human reference exists but the automated Evaluation is
  absent.
- `different summary`: both Evaluations exist but concern different summary
  artefacts.
- `unverifiable summary`: the automated Evaluation does not contain usable
  summary lineage.

If a human reference points to an Extraction that is no longer stored,
calibration stops with an error. It does not substitute a newer summary.

This matters when using `--force`. Regenerating a summary replaces its stored
Extraction ID. Any existing human judgement describes the old text and must be
recorded again against the new Extraction before calibration.

## Draw a conclusion carefully

Automated model comparison and calibration answer related but different
questions:

- Comparison identifies which summaries the judge scores most highly.
- Calibration estimates how credible that judge is relative to the reference
  editor.

A model with the highest automated score is not automatically the editorially
best model. Prefer conclusions supported by good reference coverage, low overall
and dimension error, limited systematic bias, and direct inspection of the
remaining disagreements.
