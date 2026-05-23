# Reproducibility

This page describes two workflows:

- Reproduce the paper tables from the included raw records.
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

The script uses `results/raw/lcb_hard_full` and `experiments/configs/pricing.yaml` by default. To use a different checkpoint:

```bash
bash scripts/reproduce_paper_tables.sh path/to/checkpoint
```

The output files are written to `results/processed/`.

## Manual Table Commands

Complete-case metrics:

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

Run the hard-task configuration:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_hard_100.txt \
  --checkpoint results/raw/lcb_hard_full
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

The frozen run metadata under `results/raw/lcb_hard_full/` records the model identifiers, CLI versions, task list, benchmark config, and timestamps used by the paper run.
