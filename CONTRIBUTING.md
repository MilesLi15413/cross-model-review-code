# Contributing

This repository is primarily a research artifact, so changes should preserve reproducibility.

## Development Setup

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

## Data Policy

- Keep raw paper records under `results/raw/lcb_hard_full/` auditable and immutable unless intentionally regenerating the artifact.
- Do not commit local benchmark checkouts under `external/`.
- Do not commit Python caches, temporary checkpoints, local paper exports, or exploratory runs.
- Update `docs/REPRODUCIBILITY.md` when changing commands that affect paper-facing tables.

## Pull Request Checklist

- Run `python -m pytest tests`.
- Run `bash scripts/reproduce_paper_tables.sh` if analysis code, pricing, or result records changed.
- Keep README and docs consistent with the LiveCodeBench-only paper scope.
