"""Read-only check: grade Claude's review of 3784 with sortedcontainers available.
Run: pip install --target /tmp/extra_libs sortedcontainers; PYTHONPATH=/tmp/extra_libs:external/livecodebench .venv/bin/python <this>
Result 2026-11-22: passes (twice). Main grading env unchanged; official count stays 1/162."""
import sys, glob
sys.path.insert(0, ".")
import experiments.run_regression60_reviews as m
from analysis.evaluate_writer_artifacts import _score_chunk
def main():
    d = "results/raw/regression60_reviews/R_gemini_by_claude"
    r = [x for x in m.CostTracker().load_all(d) if x.task_id == "3784"][0]
    print("stored passed:", r.passed, "| draft passed:", r.writer_passed, "| uses sortedcontainers:", "sortedcontainers" in r.final_artifact)
    for label, code in [("review as graded", r.final_artifact)]:
        res, err = _score_chunk([(r, code)], m.CONFIG, m.BENCH_CONFIG, chunk_timeout_s=1800, record_timeout_s=600, label=label)
        print(label, "->", res, err)
if __name__ == "__main__":
    main()
