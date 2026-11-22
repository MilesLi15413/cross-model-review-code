Regrade with the paper's own code (commit 6581226), mirroring its in-run batch grading
(`run_experiment._run_condition_batch_eval` -> `adapter.evaluate_batch`, 4 workers, paper configs).

    git worktree add --detach /tmp/paper_code 6581226
    ln -s "$PWD/external" /tmp/paper_code/external
    cd /tmp/paper_code
    PYTHONPATH=/tmp/paper_code:<repo>/external/livecodebench <repo>/.venv/bin/python \
      <repo>/scripts/paper_code_regrade/paper_batch_regrade.py <repo>/results/raw/lcb_hard_full/B2_gpt55_solo out
    # per-test metadata:
    ... paper_batch_meta.py <same src> out_meta.json

Result (2026-11-22): reproduces the paper (46/82 vs 44/82 stored); all 15 disputed programs fail
with "invalid syntax" because their stored code is wrapped in a ```python fence, which the paper's
in-run batch grading did not strip. Only deviation from the paper: Python 3.14 (paper's version unrecorded).
