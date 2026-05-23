#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.10}"
CHECKPOINT="${1:-results/raw/lcb_hard_full}"
PRICING_PATH="${PRICING_PATH:-experiments/configs/pricing.yaml}"
PROCESSED_DIR="${PROCESSED_DIR:-results/processed}"

echo "Using checkpoint: ${CHECKPOINT}"
echo "Using pricing:    ${PRICING_PATH}"
echo "Writing tables:   ${PROCESSED_DIR}"

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${CHECKPOINT}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_complete_case.csv" \
  --json-output "${PROCESSED_DIR}/metrics_complete_case.json" \
  --report

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${CHECKPOINT}" \
  --analysis-set all \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_all.csv" \
  --json-output "${PROCESSED_DIR}/metrics_all.json" \
  --report

"${PYTHON_BIN}" analysis/statistical_tests.py \
  --input "${CHECKPOINT}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/stats_complete_case.csv" \
  --spd-output "${PROCESSED_DIR}/spd_ci_complete_case.csv"

"${PYTHON_BIN}" analysis/statistical_tests.py \
  --input "${CHECKPOINT}" \
  --analysis-set all \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/stats_all.csv" \
  --spd-output "${PROCESSED_DIR}/spd_ci_all.csv"

echo "Done."
