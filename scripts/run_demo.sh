#!/usr/bin/env bash
# Limited demo. These stages call paid models; run each one only after approval.
#   bash scripts/run_demo.sh gemini   # Gemini in the workflow (12 calls)
#   bash scripts/run_demo.sh labels   # authorship labels (72 calls: true, none, and both false labels)
#   bash scripts/run_demo.sh help     # help-request tracking (15 calls)
#   bash scripts/run_demo.sh help2    # help requests with uncertainty types (15 calls)
# After a usage limit stops a stage, rerun the same stage to continue.
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
export PYTHONPATH="${PWD}/external/livecodebench"
CONFIG=experiments/configs/three_model_conditions.yaml

run_or_resume() {
  local checkpoint="$1"
  shift
  if [ -f "${checkpoint}/run_meta.json" ]; then
    "${PYTHON_BIN}" experiments/run_experiment.py --resume "${checkpoint}" --confirm-resume --workers 1
  else
    "${PYTHON_BIN}" experiments/run_experiment.py --benchmark livecodebench --skip-eval --skip-preflight \
      --stop-on-limit --workers 1 --checkpoint "${checkpoint}" "$@"
  fi
}

case "${1:-}" in
  gemini)
    run_or_resume results/raw/demo_gemini --config "${CONFIG}" \
      --tasks experiments/configs/test_one.txt \
      --conditions B3_gemini_solo,C5_claude_writes_gemini_reviews,C6_gemini_writes_claude_reviews,C7_gpt55_writes_gemini_reviews,C8_gemini_writes_gpt55_reviews,C9_gemini_writes_gemini_reviews
    run_or_resume results/raw/demo_gemini_draft2 --config "${CONFIG}" \
      --tasks experiments/configs/demo_gemini_draft2.txt --conditions B3_gemini_solo
    "${PYTHON_BIN}" analysis/evaluate_completed_lcb.py --input results/raw/demo_gemini
    "${PYTHON_BIN}" analysis/evaluate_completed_lcb.py --input results/raw/demo_gemini_draft2
    "${PYTHON_BIN}" analysis/evaluate_writer_artifacts.py --input results/raw/demo_gemini
    "${PYTHON_BIN}" analysis/compute_metrics.py --input results/raw/demo_gemini --analysis-set all \
      --output results/processed/demo_gemini_metrics.csv --report
    ;;
  labels)
    if [ -f results/raw/demo_labels/run_meta.json ]; then
      "${PYTHON_BIN}" experiments/run_label_study.py --resume results/raw/demo_labels --skip-preflight
    else
      "${PYTHON_BIN}" experiments/run_label_study.py --stop-on-limit --skip-preflight \
        --manifest experiments/configs/label_demo_drafts.yaml --checkpoint results/raw/demo_labels
    fi
    "${PYTHON_BIN}" analysis/label_study_metrics.py --input results/raw/demo_labels \
      --output-prefix results/processed/label_study_demo
    ;;
  help)
    run_or_resume results/raw/demo_help --config experiments/configs/help_request_conditions.yaml \
      --tasks experiments/configs/demo_help_5.txt
    "${PYTHON_BIN}" analysis/evaluate_completed_lcb.py --input results/raw/demo_help
    "${PYTHON_BIN}" analysis/help_requests.py --input results/raw/demo_help \
      --output-prefix results/processed/help_requests_demo
    ;;
  help2)
    run_or_resume results/raw/demo_help_v2 --config experiments/configs/help_request_conditions_v2.yaml \
      --tasks experiments/configs/demo_help_5.txt
    "${PYTHON_BIN}" analysis/evaluate_completed_lcb.py --input results/raw/demo_help_v2
    "${PYTHON_BIN}" analysis/help_requests.py --input results/raw/demo_help_v2 \
      --output-prefix results/processed/help_requests_v2_demo
    ;;
  *)
    echo "Usage: bash scripts/run_demo.sh {gemini|labels|help|help2}" >&2
    exit 2
    ;;
esac
