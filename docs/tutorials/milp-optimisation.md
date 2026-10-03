# Compare Greedy and MILP Optimisation

The `milp` strategy uses the same candidates, settings, and objective as
`greedy`, but solves for the best article *set* jointly. It uses SciPy's
mixed-integer programming interface and the HiGHS solver. A successful run
reports an optimal solution for this model; a solver failure does not store a
partial proposal.

Choose one strategy in the publication configuration:

```yaml
optimisation:
  strategy: milp
  settings:
    max_articles: 12
    relevance_target_score: 40
    reading_time_target_minutes: 240
    reading_time_weight: 3
    mandatory_terms: [statistics, industry]
    mandatory_terms_weight: 5
    source_diversity_max_per_source: 2
    source_diversity_weight: 2
```

Run `editorial optimise --config publication.yaml --db editorial.sqlite`, or
select **MILP** in the configuration editor and use **Run optimisation** in the
workspace. One run still creates one immutable OptimisationRequest and one
IssueProposal. To compare strategies, run each against the same database and
evidence with a different `strategy`, then use `editorial proposal compare` on
the resulting proposal IDs. Earlier proposals are retained.

MILP represents each candidate with a binary selection variable. Additional
variables represent distinct mandatory terms covered, absolute deviation from
the total reading-time target, and excess articles per source. Constraints
implement the hard article cap; the optional hard relevance minimum filters
candidates before solving. The other settings remain soft rewards or penalties. See
[How Greedy Optimisation Selects Articles](greedy-optimisation.md) for the exact
shared objective, parameter defaults, and candidate evidence.
MILP requires non-negative objective weights.

For example, suppose the reading-time target is 10 minutes with weight `3`:

| Article | Relevance | Minutes |
| --- | ---: | ---: |
| A | 10 | 10 |
| B | 9 | 5 |
| C | 9 | 5 |

With a two-article cap, greedy selects A first (objective `10`) and cannot
improve by adding B or C. MILP selects B and C together (objective `18`).
This is why the MILP result can improve on a greedy proposal even though both
use the same model.

MILP does not guarantee that more articles will be selected. It can still
return an empty or one-article proposal when that maximises the configured
objective. In particular, full-paper reading times can dominate a newsletter
reading-time target. Missing reading-time evidence still counts as zero, and
publication-level policy fields are not applied as candidate filters. The
solver may take longer than greedy on large candidate sets, and equal-scoring
optimal sets need not have the same membership.
