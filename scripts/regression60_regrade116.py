"""Free check: regrade the paper's frozen final programs for all 116 complete-case
problems x 6 conditions with the current grader, and compare with the stored `passed`.

Read-only on results/raw/lcb_*; writes results/processed/regression60_paper_regrade_116.csv
and prints per-condition pass counts (paper vs regrade). Resumable: rows already in the
CSV are kept.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.evaluate_writer_artifacts import _score_chunk  # noqa: E402
from harness.core.tracker import TaskRecord  # noqa: E402

MANIFEST = ROOT / "results/processed/pooled_manifest.csv"
OUT = ROOT / "results/processed/regression60_paper_regrade_116.csv"
DIRS = {"hard": "results/raw/lcb_hard_full", "medium": "results/raw/lcb_medium_100"}
FIELDS = ["problem_id", "slice", "condition", "paper_passed", "regrade_passed", "agrees", "source_record_path", "eval_error"]


def main() -> None:
    rows = [r for r in csv.DictReader(MANIFEST.open()) if r["in_complete_case"] == "True"]
    done = {}
    if OUT.exists():
        done = {(r["problem_id"], r["condition"]): r for r in csv.DictReader(OUT.open())}
    by_cond: dict[str, list] = {}
    for r in rows:
        if (r["source_task_id"], r["condition"]) in done:
            continue
        path = f"{DIRS[r['slice']]}/{r['condition']}/{r['source_task_id']}__{r['condition']}.json"
        by_cond.setdefault(r["condition"], []).append((r, path))

    out = list(done.values())
    for cond, items in sorted(by_cond.items()):
        pairs, meta = [], {}
        for r, path in items:
            rec = TaskRecord(**json.loads((ROOT / path).read_text()))
            pairs.append((rec, rec.final_artifact))
            meta[rec.task_id] = (r, path, rec.passed)
        results, errors = _score_chunk(pairs, "experiments/configs/all_conditions.yaml",
                                       "experiments/configs/livecodebench.yaml", 1800, 300, cond)
        for tid, (r, path, paper) in meta.items():
            reg = results.get(tid)
            out.append({"problem_id": tid, "slice": r["slice"], "condition": cond,
                        "paper_passed": paper, "regrade_passed": "" if reg is None else reg,
                        "agrees": "" if reg is None else (paper == reg),
                        "source_record_path": path, "eval_error": errors.get(tid, "")})
        with OUT.open("w", newline="") as fh:  # checkpoint after each condition
            w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerows(out)

    print(f"{'condition':<34}{'paper':>7}{'regrade':>9}{'flips F->T':>12}{'flips T->F':>12}{'errors':>8}")
    for cond in sorted({r["condition"] for r in out}):
        c = [r for r in out if r["condition"] == cond]
        p = sum(str(r["paper_passed"]) == "True" for r in c)
        g = sum(str(r["regrade_passed"]) == "True" for r in c)
        ft = sum(str(r["paper_passed"]) == "False" and str(r["regrade_passed"]) == "True" for r in c)
        tf = sum(str(r["paper_passed"]) == "True" and str(r["regrade_passed"]) == "False" for r in c)
        e = sum(bool(r["eval_error"]) for r in c)
        print(f"{cond:<34}{p:>4}/{len(c):<3}{g:>5}/{len(c):<3}{ft:>12}{tf:>12}{e:>8}")


if __name__ == "__main__":
    main()
