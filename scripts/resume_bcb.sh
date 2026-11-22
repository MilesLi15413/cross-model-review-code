#!/bin/zsh
# Resume the BigCodeBench follow-up (approved run: 80 tasks; caps keep new spend within
# Gemini $30 / OpenAI $13). Safe to run any number of times: finished drafts and reviews
# are skipped, never re-paid. Needs Docker Desktop running (for grading).
# Keeps the Mac awake while it runs (caffeinate). Log: results/raw/regression60_bcb_full.log
set -e
cd "$(dirname "$0")/.."
export PATH="$PATH:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin"
docker info >/dev/null 2>&1 || { echo "Start Docker Desktop first, wait for 'Engine running', then rerun."; exit 1; }
L=results/raw/regression60_bcb_full.log
REV=(--benchmark bigcodebench --checkpoint results/raw/regression60_bcb_reviews
     --inventory results/processed/regression60_bcb_draft_inventory.csv
     --template harness/prompts/reviewer_bcb.txt)
caffeinate -i zsh -c "
set -e
echo \"=== resume \$(date)\"
for pass in 1 2; do .venv/bin/python -u experiments/run_bcb_writers.py write --workers 3 --max-spend gemini=8 --max-spend gpt55=4; done
.venv/bin/python -u experiments/run_bcb_writers.py grade
.venv/bin/python experiments/run_bcb_writers.py inventory
for pass in 1 2; do PYTHONPATH=external/livecodebench .venv/bin/python -u experiments/run_regression60_reviews.py ${REV[*]} --reviewers gemini,gpt55,claude --drafts all --workers 4 --max-spend gemini=25 --max-spend gpt55=10 --skip-eval; done
.venv/bin/python -u experiments/run_regression60_reviews.py ${REV[*]} --grade-only
echo \"=== DONE \$(date)\"
" 2>&1 | tee -a $L
