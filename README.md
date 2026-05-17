# Cross-Model Review Code Artifact

This private repository contains the runnable code and data artifact for the LiveCodeBench study of role-assigned Claude and Codex review workflows.

The paper lives in a separate repository so Overleaf can sync only the LaTeX source. This repository is for the experiment harness, prompts, task lists, pricing assumptions, analysis scripts, and LiveCodeBench result records.

## Contents

- `harness/`: writer-reviewer pipeline, CLI runners, parsers, trackers, and the LiveCodeBench adapter.
- `experiments/`: condition configs, LiveCodeBench task lists, pricing configuration, and the experiment runner.
- `analysis/`: metric, cost, confidence-interval, and statistical-test scripts.
- `results/`: raw LiveCodeBench runs and processed CSV/JSON tables used by the paper.
- `tests/`: unit tests for the harness and analysis code.

## Primary Commands

Recompute the paper-facing metrics with current pricing:

```bash
python3.10 analysis/compute_metrics.py --input results/raw/lcb_hard_full --report --recompute-costs
```

Regenerate statistical tables:

```bash
python3.10 analysis/statistical_tests.py --input results/raw/lcb_hard_full --out results/processed/stats_complete_case.csv
```

Run the unit tests:

```bash
python3.10 -m pytest tests
```

## Notes

The manuscript focuses on LiveCodeBench only. Earlier exploratory material outside that scope is intentionally not included.
