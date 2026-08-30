# Reproducibility

This page describes three workflows:

- Reproduce the paper tables from the included raw records (no benchmark needed).
- Reproduce the same-candidate reviewer transitions (needs the benchmark, no model
  CLIs).
- Run a new LiveCodeBench experiment with the same harness.

## Analysis-Only Reproduction

Use this path when you only want to audit the frozen results. It does not require Claude Code, Codex CLI, or LiveCodeBench evaluation.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
bash scripts/reproduce_paper_tables.sh
```

The script pools `results/raw/lcb_hard_full` and `results/raw/lcb_medium_100` into the
paper's 116-task complete case, and also writes per-slice tables. To use different
checkpoints:

```bash
bash scripts/reproduce_paper_tables.sh path/to/hard path/to/medium
```

The output files are written to `results/processed/`.

## Same-Candidate Transitions

Condition-level metrics compare a reviewed pipeline against an independently sampled
solo pipeline. To measure what a reviewer did to the draft it actually received, score
each record's stored writer draft and pair the two outcomes:

```bash
bash scripts/reproduce_review_transitions.sh
```

This needs LiveCodeBench (run `./setup.sh` first) but no model CLIs. It fills in
`writer_passed` on the raw records and writes `review_transitions_*.csv` to
`results/processed/`. Records already carrying `writer_passed` are skipped, so the
script is safe to re-run; pass `--rerun` to `analysis/evaluate_writer_artifacts.py` to
force a re-score.

By default it also re-scores each stored final artifact in the same pass and saves it
as `extra.final_passed_recheck`, so any disagreement with the frozen `passed` value is
reported instead of quietly changing the numbers. The frozen `passed` field is never
overwritten.

A note on evaluation isolation: artifacts are scored in a fresh interpreter, not a
forked child. LiveCodeBench runs candidate programs through its own multiprocessing
pool, and when that pool starts inside a forked process it reports every sample as
failing rather than raising.

## Manual Table Commands

Pooled complete-case metrics (the paper's table):

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full results/raw/lcb_medium_100 \
  --input-label hard --input-label medium \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path experiments/configs/pricing.yaml \
  --output results/processed/metrics_pooled_complete_case.csv \
  --json-output results/processed/metrics_pooled_complete_case.json \
  --manifest-output results/processed/pooled_manifest.csv \
  --report
```

A single `--input` analyses that slice alone with unnamespaced task ids, which is how
the hard-slice tables are produced:

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path experiments/configs/pricing.yaml \
  --output results/processed/metrics_complete_case.csv \
  --json-output results/processed/metrics_complete_case.json \
  --report
```

Reliability-inclusive records:

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full \
  --analysis-set all \
  --recompute-costs \
  --pricing-path experiments/configs/pricing.yaml \
  --output results/processed/metrics_all.csv \
  --json-output results/processed/metrics_all.json \
  --report
```

Pairwise tests and score-per-dollar intervals:

```bash
python3.10 analysis/statistical_tests.py \
  --input results/raw/lcb_hard_full \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path experiments/configs/pricing.yaml \
  --output results/processed/stats_complete_case.csv \
  --spd-output results/processed/spd_ci_complete_case.csv
```

The paper's reliability-inclusive success rate is not the `pass_rate` column in `metrics_all.csv`. It is:

```text
passed / n_total
```

`pass_rate` in `metrics_all.csv` remains the pass rate among evaluated records, while `n_total - n_evaluated` records are invalid or incomplete outputs.

## Full Experiment Reproduction

Full reproduction requires live model calls and benchmark evaluation. Results may drift with model, CLI, benchmark, and pricing changes.

Install dependencies and clone LiveCodeBench:

```bash
./setup.sh
```

Run the two task configurations the paper pools:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_hard_100.txt \
  --checkpoint results/raw/lcb_hard_full
```

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_medium_100.txt \
  --checkpoint results/raw/lcb_medium_100
```

The runner will:

- Run CLI preflight checks once per checkpoint.
- Execute every condition in `experiments/configs/all_conditions.yaml`.
- Retry timed-out or invalid task attempts according to the harness policy.
- Record raw outputs, prompt hashes, CLI versions, timing fields, token counts, cost fields, and evaluation results.

## Pricing and Drift

The raw records preserve token counts. Paper-facing costs are recomputed from `experiments/configs/pricing.yaml` so that pricing assumptions are explicit and updateable.

For archival reproduction, record:

- Commit SHA.
- Python version.
- Claude Code CLI version.
- Codex CLI version.
- LiveCodeBench release or shard state.
- Pricing file revision.

The frozen run metadata under `results/raw/lcb_hard_full/` and
`results/raw/lcb_medium_100/` records the model identifiers, CLI versions, task list,
benchmark config, and timestamps used by each paper run.
