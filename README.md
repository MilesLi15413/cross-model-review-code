# When Should Coding Agents Review Each Other?

This repository is the code and data artifact for the paper **"When Should Coding Agents Review Each Other? A Controlled Study of Cross-Model Static Code Review."**

The study evaluates a simple writer-reviewer workflow for AI coding agents on hard LiveCodeBench code-generation tasks. One agent writes a Python solution, an optional second agent reviews it without running tests, and LiveCodeBench evaluates only the final artifact. The main question is whether review helps, and whether the writer-reviewer direction matters.

## Repository Layout

```text
analysis/                  Metrics, statistical tests, plotting, and result browsing.
experiments/configs/        Conditions, sampled task lists, benchmark config, and pricing.
experiments/run_experiment.py
                           Main experiment runner.
harness/                    Prompting, parsing, CLI execution, tracking, and benchmark adapters.
harness/prompts/            Fixed writer and reviewer prompt templates.
results/raw/lcb_hard_full/  Frozen raw run records used by the paper.
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

Recompute the paper tables from the frozen LiveCodeBench run:

```bash
bash scripts/reproduce_paper_tables.sh
```

The script refreshes:

- `results/processed/metrics_complete_case.csv`
- `results/processed/metrics_complete_case.json`
- `results/processed/metrics_all.csv`
- `results/processed/metrics_all.json`
- `results/processed/stats_complete_case.csv`
- `results/processed/stats_all.csv`
- `results/processed/spd_ci_complete_case.csv`
- `results/processed/spd_ci_all.csv`

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for exact commands and full-run notes.

## Running a New LiveCodeBench Experiment

Run setup once to install dependencies, clone LiveCodeBench under `external/`, and check the model CLIs:

```bash
./setup.sh
```

Run the hard-task configuration used by the paper:

```bash
python3.10 experiments/run_experiment.py \
  --benchmark livecodebench \
  --tasks experiments/configs/lcb_hard_100.txt \
  --checkpoint results/raw/lcb_hard_full
```

The runner records raw stdout and stderr, final artifacts, prompt hashes, CLI versions, timestamps, retry metadata, token counts, costs, parsing status, and evaluation results.

## Recomputing Metrics Manually

Complete-case metrics:

```bash
python3.10 analysis/compute_metrics.py \
  --input results/raw/lcb_hard_full \
  --analysis-set complete-case \
  --recompute-costs \
  --output results/processed/metrics_complete_case.csv \
  --json-output results/processed/metrics_complete_case.json \
  --report
```

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
