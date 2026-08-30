# Results Summary

The paper's headline numbers come from **pooling two LiveCodeBench slices**: the hard
run (`results/raw/lcb_hard_full`, 82 attempted tasks) and the medium run
(`results/raw/lcb_medium_100`, 55 attempted tasks). Task identifiers are namespaced by
slice before pooling, so ids from different slices are never paired with each other.

Two complementary views are reported for each analysis set:

- **Complete-case analysis:** tasks for which all six conditions produced valid
  evaluated answers.
- **Reliability-inclusive analysis:** all attempted tasks, with invalid outputs
  treated as failures.

Before reading the tables, see [SCOPE.md](SCOPE.md) for what these numbers do and do
not identify.

## Pooled Complete-Case Metrics (paper table)

116 shared tasks: 61 from the hard slice and 55 from the medium slice.

| Paper label | Repository condition | Passed | Pass rate | SID | Cost/task | Latency/task | Score/$ | Cross-condition regression rate |
|-------------|----------------------|--------|-----------|-----|-----------|--------------|---------|----------------------------------|
| A | `B1_claude_solo` | 106/116 | 91.4% | -- | $0.226 | 86.2s | 4.04 | -- |
| O | `B2_gpt55_solo` | 83/116 | 71.6% | -- | $0.190 | 38.5s | 3.77 | -- |
| AO | `C1_claude_writes_gpt55_reviews` | 96/116 | 82.8% | -8.6 pp | $0.382 | 118.0s | 2.17 | 11.2% |
| OA | `C2_gpt55_writes_claude_reviews` | 104/116 | 89.7% | +18.1 pp | $0.443 | 112.4s | 2.03 | 4.3% |
| AA | `C3_claude_writes_claude_reviews` | 106/116 | 91.4% | +0.0 pp | $0.389 | 135.8s | 2.35 | 2.6% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 98/116 | 84.5% | +12.9 pp | $0.312 | 67.9s | 2.71 | 5.2% |

Main takeaways, stated as pipeline contrasts:

- With Codex as writer, the reviewed pipelines beat Codex solo: OA at 89.7% and OO at
  84.5% against 71.6%. Both survive multiplicity correction.
- With Claude as writer, review did not pay: the AO pipeline came in 8.6 pp below
  Claude solo, and the AA pipeline matched Claude solo while costing more and taking
  longer.
- The direct AO-versus-OA contrast is **not** significant after correction
  (`p_BH = .1444`), so the two cross-model orderings are not shown to be separable as
  standalone conditions on this sample.

## Reading "cross-condition regression rate"

The `cross_condition_regression_rate` column counts tasks where the reviewed pipeline
failed and the **independently sampled** solo pipeline of the same writer passed. Both
arms drew their own writer output, so the two programs are usually different. The
column therefore measures a transition between two whole pipelines. It is not evidence
that a reviewer broke the draft it was handed, and it should not be described as a
reviewer-induced regression.

The columns `regression_rate` and `regressions` are deprecated aliases for the same
numbers, kept for one release so older scripts keep working.

For the reviewer-attributable quantity, see the next section.

## Same-Candidate Reviewer Transitions

`analysis/evaluate_writer_artifacts.py` scores the writer draft stored on every
record — the exact program its reviewer received — and
`analysis/review_transitions.py` turns those into before/after pairs on one fixed
candidate. These tables are not pre-generated in the repository, because producing
them requires the LiveCodeBench evaluator rather than only the stored records. Build
them with:

```bash
bash scripts/reproduce_review_transitions.sh
```

That fills in `writer_passed` on the raw records (never touching the frozen `passed`
field) and writes:

- `results/processed/review_transitions_pooled.csv`
- `results/processed/review_transitions_hard.csv`
- `results/processed/review_transitions_medium.csv`

Columns: `reviewer_fix` (draft failed, final passed), `reviewer_regression` (draft
passed, final failed), `kept_pass`, `kept_fail`, plus `unchanged_artifact` (the
reviewer returned the draft verbatim) and `n_unscorable` (no scorable draft stored).
`cross_condition_fixes` and `cross_condition_regressions` are carried alongside so the
two quantities can be compared directly on the same rows.

## Hard-Slice Complete-Case Metrics

61 shared hard tasks.

| Paper label | Repository condition | Passed | Pass rate | Cost/task | Latency/task | Score/$ | Cross-condition regression rate |
|-------------|----------------------|--------|-----------|-----------|--------------|---------|----------------------------------|
| A | `B1_claude_solo` | 53/61 | 86.9% | $0.282 | 108.5s | 3.08 | -- |
| O | `B2_gpt55_solo` | 36/61 | 59.0% | $0.242 | 54.3s | 2.44 | -- |
| AO | `C1_claude_writes_gpt55_reviews` | 46/61 | 75.4% | $0.404 | 127.0s | 1.87 | 16.4% |
| OA | `C2_gpt55_writes_claude_reviews` | 53/61 | 86.9% | $0.496 | 145.7s | 1.75 | 6.6% |
| AA | `C3_claude_writes_claude_reviews` | 55/61 | 90.2% | $0.469 | 167.7s | 1.92 | 1.6% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 49/61 | 80.3% | $0.352 | 91.6s | 2.28 | 8.2% |

On the hard slice alone, OA versus O reaches `p_BH = .004555`, while AO versus A does
not reach adjusted significance (`p_BH = .197448`). The negative AO association is
therefore carried largely by the pooled sample, not by the hard slice on its own.

## Medium-Slice Complete-Case Metrics

55 shared medium tasks.

| Paper label | Repository condition | Passed | Pass rate |
|-------------|----------------------|--------|-----------|
| A | `B1_claude_solo` | 53/55 | 96.4% |
| O | `B2_gpt55_solo` | 47/55 | 85.5% |
| AO | `C1_claude_writes_gpt55_reviews` | 50/55 | 90.9% |
| OA | `C2_gpt55_writes_claude_reviews` | 51/55 | 92.7% |
| AA | `C3_claude_writes_claude_reviews` | 51/55 | 92.7% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 49/55 | 89.1% |

## Reliability-Inclusive View (hard slice)

The frozen hard run attempted 82 tasks. Invalid outputs include CLI errors, timeouts,
parse failures, budget failures, or empty final artifacts.

| Paper label | Repository condition | Evaluated | Passed | Invalid | Success rate (`passed / 82`) | Valid rate |
|-------------|----------------------|-----------|--------|---------|-------------------------------|------------|
| A | `B1_claude_solo` | 65 | 55 | 17 | 67.1% | 79.3% |
| O | `B2_gpt55_solo` | 78 | 44 | 4 | 53.7% | 95.1% |
| AO | `C1_claude_writes_gpt55_reviews` | 67 | 48 | 15 | 58.5% | 81.7% |
| OA | `C2_gpt55_writes_claude_reviews` | 76 | 62 | 6 | 75.6% | 92.7% |
| AA | `C3_claude_writes_claude_reviews` | 67 | 60 | 15 | 73.2% | 81.7% |
| OO | `C4_gpt55_writes_gpt55_reviews` | 80 | 60 | 2 | 73.2% | 97.6% |

Reliability-inclusive analysis changes the deployment ranking on this slice: Codex
output reviewed by Claude has the strongest overall success rate, while Codex
self-review has the strongest validity rate among reviewed conditions.

## Pairwise Tests

Selected pooled complete-case McNemar results (`stats_pooled_complete_case.csv`):

| Comparison | First only | Second only | p-value | BH-adjusted p-value |
|------------|------------|-------------|---------|---------------------|
| A vs O | 24 | 1 | 0.000002 | 0.000015 |
| OA vs O | 26 | 5 | 0.000192 | 0.000960 |
| AA vs O | 24 | 1 | 0.000002 | 0.000015 |
| OO vs O | 21 | 6 | 0.005925 | 0.022219 |
| A vs AO | 13 | 3 | 0.021271 | 0.045581 |
| AA vs AO | 12 | 2 | 0.012939 | 0.032348 |
| OA vs AO | 13 | 5 | 0.096252 | 0.144378 |

Full tables are in:

- `results/processed/stats_pooled_complete_case.csv`
- `results/processed/spd_ci_pooled_complete_case.csv`
- `results/processed/stats_complete_case.csv` (hard slice)
- `results/processed/stats_all.csv` (hard slice)

## Recompute These Results

```bash
bash scripts/reproduce_paper_tables.sh
```

The recomputation uses token counts in raw records and pricing assumptions from
`experiments/configs/pricing.yaml`.
