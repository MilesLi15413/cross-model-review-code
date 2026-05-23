# Artifact Guide

This repository is structured as an auditable research artifact for the LiveCodeBench study reported in the paper.

## Scope

Included:

- Fixed writer and reviewer prompt templates.
- Experimental condition configuration.
- LiveCodeBench task lists used during development and the paper run.
- Raw per-task records for the frozen hard-task run.
- Processed metrics and statistical-test tables.
- Analysis scripts and unit tests.

Not included:

- Local benchmark checkouts under `external/`.
- Local paper source or Overleaf exports.
- Python caches, temporary runs, and exploratory outputs outside the paper scope.

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
- `experiments/configs/pricing.yaml`: pricing assumptions used when recomputing paper-facing costs from token counts.
- `harness/prompts/writer_lcb.txt`: fixed writer prompt template.
- `harness/prompts/reviewer_lcb.txt`: fixed reviewer prompt template.
- `results/raw/lcb_hard_full/`: raw frozen run records used for paper tables.
- `results/processed/`: processed CSV and JSON tables derived from raw records.

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
- Final LiveCodeBench pass/fail result.

The raw records are intentionally verbose so that downstream readers can audit both correctness and reliability failures.

## Processed Tables

The most important processed files are:

- `metrics_complete_case.csv`: paper-facing complete-case metrics over tasks with valid answers for all six conditions.
- `metrics_all.csv`: all attempted records with invalid outputs excluded from the evaluated denominator. The reliability-inclusive success rate in the paper is `passed / n_total`.
- `stats_complete_case.csv`: pairwise McNemar tests with Benjamini-Hochberg correction.
- `spd_ci_complete_case.csv`: bootstrap confidence intervals for score per dollar.

Run `bash scripts/reproduce_paper_tables.sh` to refresh these outputs.
