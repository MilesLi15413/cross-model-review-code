#!/usr/bin/env bash
# Same-candidate reviewer transitions.
#
# Unlike scripts/reproduce_paper_tables.sh, this path needs the LiveCodeBench
# evaluator (see setup.sh) because it re-scores each stored writer draft. It does
# not call any model CLI. The scoring step is idempotent: records that already have
# writer_passed are skipped unless --rerun is passed to the evaluator.
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.10}"
HARD_CHECKPOINT="${1:-results/raw/lcb_hard_full}"
MEDIUM_CHECKPOINT="${2:-results/raw/lcb_medium_100}"
PROCESSED_DIR="${PROCESSED_DIR:-results/processed}"

for checkpoint in "${HARD_CHECKPOINT}" "${MEDIUM_CHECKPOINT}"; do
  echo "== Scoring stored writer drafts in ${checkpoint} =="
  "${PYTHON_BIN}" -u analysis/evaluate_writer_artifacts.py --input "${checkpoint}"
done

echo
echo "== Pooled same-candidate transitions =="
"${PYTHON_BIN}" analysis/review_transitions.py \
  --input "${HARD_CHECKPOINT}" "${MEDIUM_CHECKPOINT}" \
  --input-label hard --input-label medium \
  --analysis-set complete-case \
  --output "${PROCESSED_DIR}/review_transitions_pooled.csv" \
  --report

"${PYTHON_BIN}" analysis/review_transitions.py \
  --input "${HARD_CHECKPOINT}" \
  --analysis-set complete-case \
  --output "${PROCESSED_DIR}/review_transitions_hard.csv"

"${PYTHON_BIN}" analysis/review_transitions.py \
  --input "${MEDIUM_CHECKPOINT}" \
  --analysis-set complete-case \
  --output "${PROCESSED_DIR}/review_transitions_medium.csv"

echo "Done."
