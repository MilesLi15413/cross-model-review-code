"""Grade regression60 Gemini B3 solo drafts with the paper's grader and summarize.

Writes `passed` and `writer_passed` into the new regression60 B3 records (never the
frozen paper records). Already graded records are skipped. Free: no model calls.

  python scripts/regression60_grade_solo.py results/raw/regression60_gemini_solo [--tasks FILE]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.evaluate_writer_artifacts import _score_chunk  # noqa: E402
from harness.core.tracker import CostTracker  # noqa: E402

COND = "B3_gemini_solo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoint")
    ap.add_argument("--tasks", help="Only summarize these task ids")
    args = ap.parse_args()

    cond_dir = Path(args.checkpoint) / COND
    tracker = CostTracker(str(ROOT / "experiments/configs/pricing.yaml"))
    records = tracker.load_all(str(cond_dir))
    if args.tasks:
        wanted = set(Path(args.tasks).read_text().split())
        records = [r for r in records if r.task_id in wanted]

    todo = [r for r in records if tracker.record_is_complete(r) and r.passed is None]
    if todo:
        results, errors = _score_chunk(
            [(r, r.final_artifact) for r in todo],
            "experiments/configs/three_model_conditions.yaml",
            "experiments/configs/livecodebench.yaml",
            chunk_timeout_s=1800, record_timeout_s=300, label=COND,
        )
        for r in todo:
            if r.task_id in results:
                r.passed = r.writer_passed = results[r.task_id]
            else:
                r.extra["eval_error"] = errors.get(r.task_id, "unscored")
            tracker.save(r, str(cond_dir))

    valid = [r for r in records if tracker.record_is_complete(r)]
    costs = [r.writer_cost_usd for r in records]
    print(f"records saved: {len(records)}")
    print(f"valid: {len(valid)}  parse failures: {sum(r.parse_failed for r in records)}  "
          f"cli errors: {sum(r.cli_error for r in records)}  timeouts: {sum(r.timed_out for r in records)}  "
          f"eval errors: {sum('eval_error' in r.extra for r in records)}")
    print(f"retried tasks: {sum(r.extra.get('attempt_count', 1) > 1 for r in records)}")
    print(f"passed: {sum(bool(r.passed) for r in valid)}/{len(valid)}")
    if costs:
        print(f"cost per call: avg ${statistics.mean(costs):.4f}  max ${max(costs):.4f}  total ${sum(costs):.4f}")
        lat = [r.writer_latency_s for r in records]
        print(f"latency: avg {statistics.mean(lat):.0f}s  max {max(lat):.0f}s")
    tools = [r.extra.get("writer_runtime_settings", {}).get("tool_calls", 0) for r in records]
    models = {m for r in records for m in r.extra.get("writer_runtime_settings", {}).get("models_used", [])}
    print(f"tool calls: {sum(tools)}  models used: {sorted(models)}  "
          f"cli versions: {sorted({r.writer_cli_version for r in records})}")
    for r in sorted(records, key=lambda r: r.task_id):
        print(f"  {r.task_id:<10} {'PASS' if r.passed else 'FAIL' if r.passed is False else '----'} "
              f"${r.writer_cost_usd:.3f} {r.writer_latency_s:.0f}s in={r.writer_input_tokens} "
              f"out={r.writer_output_tokens} parse={r.writer_parse_method}")


if __name__ == "__main__":
    main()
