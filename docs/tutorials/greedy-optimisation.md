# How Greedy Optimisation Selects Articles

The `greedy` strategy produces an IssueProposal from stored Articles, Extractions,
and Evaluations. It proposes a selection; it does not approve a publication or
change article status. Each run creates a new proposal rather than modifying an
earlier one.

## Candidate Evidence

An article becomes a candidate only when it has a relevance Evaluation with a
numeric score. The latest such Evaluation supplies its score. An optional hard
minimum relevance score excludes articles below that threshold. Other evaluators,
including summary quality, do not contribute directly to this optimiser's score.

For each candidate, the optimiser uses the latest reading-time Extraction. If
there is none, reading time is treated as zero, not estimated from the article.
Mandatory terms are matched case-insensitively as substrings of the title,
summary, or content. A stored arXiv full-text Extraction is used as content when
available. Source labels determine the source-diversity counts; articles with no
source share an empty source label.

The current optimiser reads all stored articles. Values under `editorial_policy`,
such as maximum age, eligible statuses, maximum articles, and maximum reading
minutes, are not candidate filters here. Configure the corresponding optimiser
settings when they exist, and do not interpret a soft target as a hard limit.

## Objective

For a selected set of candidates `S`, define:

- `r(i)`: relevance score for article `i`;
- `t(i)`: reading minutes for article `i`;
- `covered(S)`: distinct configured mandatory terms found in any article in `S`;
- `count(s, S)`: number of articles from source `s` in `S`.

The optimiser maximises:

```text
F(S) = sum(r(i) for i in S)
     + mandatory_terms_weight * len(covered(S))
     - reading_time_weight * abs(sum(t(i) for i in S) - reading_time_target_minutes)
     - relevance_target_weight
         * sum(max(0, relevance_target_score - r(i)) for i in S)
     - source_diversity_weight
         * sum(max(0, count(s, S) - source_diversity_max_per_source) for each source s)
```

If a target or source limit is unset, its penalty term is zero. The mandatory
term reward is zero when no terms are configured. The reading-time target is a
*desired total*, not a ceiling: both undershooting and overshooting it cost
points. Relevance-target shortfalls are charged *per selected article*. A
mandatory term is rewarded only once across the entire proposal. The
per-source preference charges for each article beyond the preferred count,
but does not exclude that article.

| Group | Settings (default) | Effect |
| --- | --- | --- |
| Selection limits | `max_articles` (`8`)<br>`hard_minimum_relevance_score` (unset) | Caps the number selected; optionally excludes candidates below a score. |
| Relevance target | `relevance_target_score` (unset)<br>`relevance_target_weight` (`1`) | Sets a soft per-article score target and the cost per point below it. |
| Reading-time target | `reading_time_target_minutes` (unset)<br>`reading_time_weight` (`3`) | Sets a soft total reading-time target and the cost per minute away from it. |
| Mandatory terms | `mandatory_terms` (none)<br>`mandatory_terms_weight` (`5`) | Rewards distinct terms covered anywhere in the proposal. |
| Source diversity | `source_diversity_max_per_source` (unset)<br>`source_diversity_weight` (`2`) | Sets a preferred maximum per source and the cost for each article beyond it. |

`minimum_relevance_score` is a legacy alias for `relevance_target_score` when
the latter is unset. Despite its name, it is a soft target, not an exclusion
threshold. Use `hard_minimum_relevance_score` to exclude low-scoring articles.

## Selection Loop

The process is iterative. Initially the proposal is empty. At every iteration,
the optimiser scores the proposal formed by adding *each* remaining candidate,
chooses the one with the highest score, and adds it only if the score strictly
improves on the current proposal. It then recomputes all possible additions
against the new proposal:

```text
selected = []
remaining = eligible candidates
current_value = F(selected)

while len(selected) < max_articles and remaining:
    best = none
    best_value = current_value

    for article in remaining:
        value = F(selected + [article])
        if value > best_value:
            best = article
            best_value = value

    if best is none:
        break

    selected.append(best)
    remaining.remove(best)
    current_value = best_value

return selected
```

Every candidate is examined at each step, so a unique highest-scoring addition
does not depend on iteration order. Ties retain the first candidate encountered.
To make this repeatable, candidates are first sorted by relevance score
descending, then article URL, then article ID. The algorithm does not remove or
swap earlier choices, and it does not evaluate all possible article sets. It
may therefore miss a better combination. It can stop with zero, one, or any
number up to `max_articles`.

For example, consider a 240-minute reading-time target with weight `3`. A
selected paper of 238 minutes has a reading-time penalty of `6`. Adding a
30-minute paper raises the total to 268 minutes and that penalty to `84`: the
addition costs 78 points on reading time alone. If it contributes 41 relevance
points, covers no new mandatory terms, and changes no other penalty, the
proposal becomes 37 points worse and the optimiser will not add it. A
12-article maximum does not make the optimiser fill 12 places.

The constraint results stored with a proposal explain its final selection;
they do not introduce additional selection rules. In particular, a soft goal
can be reported as unsatisfied even though the proposal is valid. Use proposal
inspection or comparison to review outcomes after changing settings; changing
the settings alone does not refresh earlier proposals.
