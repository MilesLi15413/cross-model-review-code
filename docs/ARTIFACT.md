# Artifact Guide

This repository is structured as an auditable research artifact for the LiveCodeBench study reported in the paper.

## Scope

Included:

- Fixed writer and reviewer prompt templates.
- Experimental condition configuration.
- LiveCodeBench task lists used during development and the paper runs.
- Raw per-task records for both frozen runs the paper pools: the hard slice and the
  medium slice.
- Processed metrics, statistical-test tables, the pooled manifest, and the
  same-candidate reviewer-transition tables.
- Analysis scripts and unit tests.

What the numbers do and do not identify is stated in [SCOPE.md](SCOPE.md).

Not included:

- Local benchmark checkouts under `external/`.
- Local paper source or Overleaf exports.
- Python caches, temporary runs, and exploratory outputs outside the artifact scope.

## Condition Mapping

| Paper label | Repository condition | Writer | Reviewer |
|-------------|----------------------|--------|----------|
| A | `B1_claude_solo` | `claude-opus-4-7` | none |
| O | `B2_gpt55_solo` | `gpt-5.5` | none |
| AO | `C1_claude_writes_gpt55_reviews` | `claude-opus-4-7` | `gpt-5.5` |
| OA | `C2_gpt55_writes_claude_reviews` | `gpt-5.5` | `claude-opus-4-7` |
| AA | `C3_claude_writes_claude_reviews` | `claude-opus-4-7` | `claude-opus-4-7` |
| OO | `C4_gpt55_writes_gpt55_reviews` | `gpt-5.5` | `gpt-5.5` |

## Important Files

- `experiments/configs/all_conditions.yaml`: all six writer-reviewer conditions, effort settings, timeouts, and per-task budget caps.
- `experiments/configs/livecodebench.yaml`: LiveCodeBench dataset configuration.
- `experiments/configs/lcb_hard_100.txt`: sampled hard-task list for the paper run.
- `experiments/configs/lcb_medium_100.txt`: sampled medium-task list for the paper run.
- `experiments/configs/pricing.yaml`: pricing assumptions used when recomputing paper-facing costs from token counts.
- `harness/prompts/writer_lcb.txt`: fixed writer prompt template.
- `harness/prompts/reviewer_lcb.txt`: fixed reviewer prompt template.
- `results/raw/lcb_hard_full/`: raw frozen run records, hard slice (82 attempted tasks).
- `results/raw/lcb_medium_100/`: raw frozen run records, medium slice (55 attempted tasks).
- `results/processed/`: processed CSV and JSON tables derived from raw records.

The paper's pooled 116-task complete case is the union of the two slices, with task
ids namespaced by slice. Either slice can also be analysed on its own by passing a
single `--input`.

## Raw Record Contents

Each task-condition record is a JSON object containing, when available:

- Task and condition identifiers.
- Writer and reviewer model identifiers.
- Prompt hashes and benchmark metadata.
- Raw stdout and stderr from model CLI calls.
- Parsed final artifact and parse metadata.
- CLI version and timestamp fields.
- Retry, timeout, parse failure, CLI error, and budget flags.
- Token counts, cached-token counts, recomputed cost fields, and latency fields.
- Final LiveCodeBench pass/fail result (`passed`).
- `writer_passed`: the LiveCodeBench result of the stored writer draft, filled in by
  `analysis/evaluate_writer_artifacts.py`. This is what makes same-candidate reviewer
  fixes and regressions measurable; it is null on records whose draft has not been
  scored.
- `extra.writer_artifact_sha256`, `extra.final_artifact_sha256`, and
  `extra.reviewer_changed_artifact`: artifact digests and whether the reviewer changed
  the program at all.
- `extra.final_passed_recheck`: the final artifact re-scored in the same pass as the
  draft, so evaluator drift between the frozen run and a later re-score is visible
  rather than silent.

The raw records are intentionally verbose so that downstream readers can audit both correctness and reliability failures.

## Processed Tables

The most important processed files are:

- `metrics_pooled_complete_case.csv`: the paper's complete-case metrics over the 116
  tasks with valid answers for all six conditions in both slices.
- `pooled_manifest.csv`: one row per (slice, task, condition) showing validity,
  complete-case membership, the final and draft outcomes, and artifact digests. This
  is the audit trail for which records the pooled tables used.
- `metrics_pooled_all.csv`: all attempted records with invalid outputs excluded from
  the evaluated denominator. The reliability-inclusive success rate in the paper is
  `passed / n_total`.
- `stats_pooled_complete_case.csv`: pairwise McNemar tests with Benjamini-Hochberg
  correction.
- `spd_ci_pooled_complete_case.csv`: bootstrap confidence intervals for score per
  dollar.
- `review_transitions_pooled.csv`: same-candidate reviewer fixes and regressions,
  reported next to their cross-condition counterparts.
- `metrics_complete_case.csv`, `metrics_all.csv`, `stats_complete_case.csv`,
  `spd_ci_complete_case.csv`, `stats_all.csv`, `spd_ci_all.csv`: the same analyses on
  the hard slice alone; `metrics_medium_complete_case.csv` for the medium slice.

A note on metric names: `cross_condition_regression_rate` counts outcome flips against
an independently sampled solo run, not reviewer-induced regressions on a given draft.
`regression_rate` and `regressions` are deprecated aliases for it. The
reviewer-attributable quantity lives in `review_transitions_pooled.csv`.

Run `bash scripts/reproduce_paper_tables.sh` to refresh the metric and statistics
tables, and `bash scripts/reproduce_review_transitions.sh` to refresh the
same-candidate tables (that one needs the LiveCodeBench evaluator).
