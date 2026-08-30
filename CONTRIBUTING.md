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

- Keep raw paper records under `results/raw/lcb_hard_full/` and `results/raw/lcb_medium_100/` auditable and immutable unless intentionally regenerating the artifact. Scoring stored writer drafts is the one sanctioned in-place update: it adds `writer_passed` and `extra` fields and never rewrites the frozen `passed` result.
- Do not commit local benchmark checkouts under `external/`.
- Do not commit Python caches, temporary checkpoints, local paper exports, or exploratory runs.
- Update `docs/REPRODUCIBILITY.md` when changing commands that affect paper-facing tables.

## Pull Request Checklist

- Run `python -m pytest tests`.
- Run `bash scripts/reproduce_paper_tables.sh` if analysis code, pricing, or result records changed.
- Run `bash scripts/reproduce_review_transitions.sh` if the same-candidate analysis changed (needs the LiveCodeBench evaluator).
- Keep README and docs consistent with the LiveCodeBench-only artifact scope, and with the estimand and transfer boundary stated in `docs/SCOPE.md`.
