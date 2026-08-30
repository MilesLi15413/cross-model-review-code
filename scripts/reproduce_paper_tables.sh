#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.10}"
HARD_CHECKPOINT="${1:-results/raw/lcb_hard_full}"
MEDIUM_CHECKPOINT="${2:-results/raw/lcb_medium_100}"
PRICING_PATH="${PRICING_PATH:-experiments/configs/pricing.yaml}"
PROCESSED_DIR="${PROCESSED_DIR:-results/processed}"

echo "Hard checkpoint:   ${HARD_CHECKPOINT}"
echo "Medium checkpoint: ${MEDIUM_CHECKPOINT}"
echo "Using pricing:     ${PRICING_PATH}"
echo "Writing tables:    ${PROCESSED_DIR}"

POOLED_INPUTS=("${HARD_CHECKPOINT}" "${MEDIUM_CHECKPOINT}")
POOLED_LABELS=(--input-label hard --input-label medium)

echo
echo "== Pooled hard+medium tables (the paper's 116-task complete case) =="

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${POOLED_INPUTS[@]}" \
  "${POOLED_LABELS[@]}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_pooled_complete_case.csv" \
  --json-output "${PROCESSED_DIR}/metrics_pooled_complete_case.json" \
  --manifest-output "${PROCESSED_DIR}/pooled_manifest.csv" \
  --report

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${POOLED_INPUTS[@]}" \
  "${POOLED_LABELS[@]}" \
  --analysis-set all \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_pooled_all.csv" \
  --json-output "${PROCESSED_DIR}/metrics_pooled_all.json" \
  --report

"${PYTHON_BIN}" analysis/statistical_tests.py \
  --input "${POOLED_INPUTS[@]}" \
  "${POOLED_LABELS[@]}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/stats_pooled_complete_case.csv" \
  --spd-output "${PROCESSED_DIR}/spd_ci_pooled_complete_case.csv"

echo
echo "== Hard-slice-only tables =="

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${HARD_CHECKPOINT}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_complete_case.csv" \
  --json-output "${PROCESSED_DIR}/metrics_complete_case.json" \
  --report

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${HARD_CHECKPOINT}" \
  --analysis-set all \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_all.csv" \
  --json-output "${PROCESSED_DIR}/metrics_all.json" \
  --report

"${PYTHON_BIN}" analysis/statistical_tests.py \
  --input "${HARD_CHECKPOINT}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/stats_complete_case.csv" \
  --spd-output "${PROCESSED_DIR}/spd_ci_complete_case.csv"

"${PYTHON_BIN}" analysis/statistical_tests.py \
  --input "${HARD_CHECKPOINT}" \
  --analysis-set all \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/stats_all.csv" \
  --spd-output "${PROCESSED_DIR}/spd_ci_all.csv"

echo
echo "== Medium-slice-only tables =="

"${PYTHON_BIN}" analysis/compute_metrics.py \
  --input "${MEDIUM_CHECKPOINT}" \
  --analysis-set complete-case \
  --recompute-costs \
  --pricing-path "${PRICING_PATH}" \
  --output "${PROCESSED_DIR}/metrics_medium_complete_case.csv" \
  --json-output "${PROCESSED_DIR}/metrics_medium_complete_case.json" \
  --report

echo "Done."
