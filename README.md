# When Should Coding Agents Review Each Other?

This repository is the code and data artifact for the paper **"When Should Coding Agents Review Each Other? A Controlled Study of Cross-Model Static Code Review."**

The study evaluates a simple writer-reviewer workflow for AI coding agents on hard and medium LiveCodeBench code-generation tasks. One agent writes a Python solution, an optional second agent reviews it without running tests, and LiveCodeBench evaluates only the final artifact. The main question is whether review helps, and whether the writer-reviewer direction matters.

## Scope and Interpretation

The artifact deliberately keeps result claims out of this README. Before drawing
conclusions from the tables, read [docs/SCOPE.md](docs/SCOPE.md): it states what the
six conditions estimate (a contrast between whole stochastic pipelines, not the effect
of review on a fixed draft), which contrasts survive multiplicity correction, and the
boundary beyond which the measurement is not established — one model pair, fixed
prompts, high reasoning effort, a single static review pass whose output replaces the
draft, no reviewer tool use, no repository context, and self-contained single-file
Python tasks scored only by hidden tests.

[docs/RESULTS.md](docs/RESULTS.md) has the paper-facing tables and interpretation notes.

## Follow-up Experiments

- [docs/AUTHORSHIP_LABEL_STUDY.md](docs/AUTHORSHIP_LABEL_STUDY.md): planned study of
  whether telling the reviewer who wrote the draft changes its review. Design only,
  not yet run.

## Repository Layout

```text
analysis/                  Metrics, statistical tests, plotting, and result browsing.
experiments/configs/        Conditions, sampled task lists, benchmark config, and pricing.
experiments/run_experiment.py
                           Main experiment runner.
harness/                    Prompting, parsing, CLI execution, tracking, and benchmark adapters.
harness/prompts/            Fixed writer and reviewer prompt templates.
results/raw/lcb_hard_full/  Frozen raw run records, hard slice (82 tasks).
results/raw/lcb_medium_100/ Frozen raw run records, medium slice (55 tasks).
results/processed/          Paper-facing CSV and JSON tables.
scripts/                    Reproduction helper scripts.
tests/                      Unit tests for the harness and analysis code.
```

Detailed artifact contents are documented in [docs/ARTIFACT.md](docs/ARTIFACT.md).

## Requirements

- Python 3.10 or newer
- Claude Code CLI with access to `claude-opus-4-7`
- Codex CLI with access to `gpt-5.5`
- Network access for downloading LiveCodeBench shards when local task JSON files are absent

For analysis-only reproduction from the included raw records, the model CLIs are not needed.

## Quick Start

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Run the test suite:

```bash
python -m pytest tests
```

Recompute the paper tables from the frozen LiveCodeBench runs:

```bash
bash scripts/reproduce_paper_tables.sh
```

The script refreshes the pooled tables the paper reports:

- `results/processed/metrics_pooled_complete_case.csv` and `.json`
- `results/processed/metrics_pooled_all.csv` and `.json`
- `results/processed/stats_pooled_complete_case.csv`
- `results/processed/spd_ci_pooled_complete_case.csv`
- `results/processed/pooled_manifest.csv` (per task-condition audit trail)

and the per-slice tables:

- `results/processed/metrics_complete_case.csv` and `.json` (hard slice)
- `results/processed/metrics_all.csv` and `.json` (hard slice)
- `results/processed/stats_complete_case.csv`, `results/processed/stats_all.csv`
- `results/processed/spd_ci_complete_case.csv`, `results/processed/spd_ci_all.csv`
- `results/processed/metrics_medium_complete_case.csv` and `.json` (medium slice)

Same-candidate reviewer transitions need the LiveCodeBench evaluator, so they have
their own script:

```bash
bash scripts/reproduce_review_transitions.sh
```

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for exact commands and full-run notes.

## Running a New LiveCodeBench Experiment

Run setup once to install dependencies, clone LiveCodeBench under `external/`, and check the model CLIs:

```bash
./setup.sh
```

Run the two task configurations used by the paper:

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

The runner records raw stdout and stderr, final artifacts, prompt hashes, CLI versions, timestamps, retry metadata, token counts, costs, parsing status, and evaluation results.

## Recomputing Metrics Manually

Pooled complete-case metrics (the paper's 116-task table):

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full results/raw/lcb_medium_100 \
  --input-label hard --input-label medium \
  --analysis-set complete-case \
  --recompute-costs \
  --output results/processed/metrics_pooled_complete_case.csv \
  --json-output results/processed/metrics_pooled_complete_case.json \
  --manifest-output results/processed/pooled_manifest.csv \
  --report
```

Passing a single `--input` analyses that slice on its own, unnamespaced.

Reliability-inclusive metrics:

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full \
  --analysis-set all \
  --recompute-costs \
  --output results/processed/metrics_all.csv \
  --json-output results/processed/metrics_all.json \
  --report
```

Pairwise tests and score-per-dollar bootstrap intervals:

```bash
python3.10 analysis/statistical_tests.py \
  --input results/raw/lcb_hard_full \
  --analysis-set complete-case \
  --recompute-costs \
  --output results/processed/stats_complete_case.csv \
  --spd-output results/processed/spd_ci_complete_case.csv
```

## Citation

Please cite the paper and this artifact if you use the code or data. Citation metadata is provided in [CITATION.cff](CITATION.cff).

## License and Reuse

This repository is released under the MIT License. See [LICENSE](LICENSE).
