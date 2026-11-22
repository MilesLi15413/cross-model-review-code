"""Step 2 (and later 5) of the regression-60 run: inventory of solo drafts.

For each of the 60 problems, lists each solo draft with its pass/fail result and
writes results/processed/regression60_draft_inventory.csv. Free: no model calls.

`passed` is the draft re-graded now with the paper's grader (the same fresh-interpreter
LiveCodeBench evaluator used for the reviewed code later), so "passed before review"
and "failed after review" come from one grader. `paper_passed` is the stored result
from the original run; `grader_agrees` flags any drift. The frozen records are only
read, never written.

  python scripts/regression60_inventory.py              # Claude + GPT-5.5 (Step 2)
  python scripts/regression60_inventory.py --gemini DIR # also add Gemini B3 drafts (Step 5)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.evaluate_writer_artifacts import _score_chunk  # noqa: E402
from harness.core.tracker import TaskRecord  # noqa: E402

TASKS = ROOT / "experiments/task_lists/lcb_regression_60.txt"
SAMPLE_LOG = ROOT / "results/processed/regression60_sample_log.json"
OUT = ROOT / "results/processed/regression60_draft_inventory.csv"
SLICE_DIRS = {"hard": "results/raw/lcb_hard_full", "medium": "results/raw/lcb_medium_100"}
ORIGINAL = {"claude": "B1_claude_solo", "gpt55": "B2_gpt55_solo"}
FIELDS = ["problem_id", "writer", "passed", "source_record_path", "paper_passed", "grader_agrees"]


def load(path: str) -> TaskRecord:
    return TaskRecord(**json.loads((ROOT / path).read_text()))


def grade(writer: str, paths: dict[str, str]) -> dict[str, bool]:
    pairs = [(rec, rec.writer_artifact) for rec in (load(p) for p in paths.values())]
    results, errors = _score_chunk(
        pairs,
        "experiments/configs/all_conditions.yaml",
        "experiments/configs/livecodebench.yaml",
        chunk_timeout_s=1800,
        record_timeout_s=300,
        label=f"{writer} drafts",
    )
    if errors:
        sys.exit(f"Grader errors for {writer}: {errors}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gemini", help="Checkpoint dir holding the regression60 B3 records")
    parser.add_argument("--tasks", default=str(TASKS))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    out_path = Path(args.out)
    task_ids = Path(args.tasks).read_text().split()
    slices = {
        r["source_task_id"]: r["slice"]
        for r in csv.DictReader((ROOT / "results/processed/pooled_manifest.csv").open())
        if r["in_complete_case"] == "True"
    }
    existing = {}
    if out_path.exists():
        existing = {(r["problem_id"], r["writer"]): r for r in csv.DictReader(out_path.open())}

    sources: dict[str, dict[str, str]] = {}
    for writer, cond in ORIGINAL.items():
        sources[writer] = {
            t: f"{SLICE_DIRS[slices[t]]}/{cond}/{t}__{cond}.json" for t in task_ids
        }
    if args.gemini:
        sources["gemini"] = {
            t: str(Path(args.gemini) / "B3_gemini_solo" / f"{t}__B3_gemini_solo.json")
            for t in task_ids
        }

    rows = []
    for writer, paths in sources.items():
        todo = {t: p for t, p in paths.items() if (t, writer) not in existing}
        graded = grade(writer, todo) if todo else {}
        for t in task_ids:
            if (t, writer) in existing:
                rows.append(existing[(t, writer)])
                continue
            rec = load(paths[t])
            paper = rec.passed if writer in ORIGINAL else None
            rows.append({
                "problem_id": t,
                "writer": writer,
                "passed": graded[t],
                "source_record_path": paths[t],
                "paper_passed": "" if paper is None else paper,
                "grader_agrees": "" if paper is None else paper == graded[t],
            })

    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {out_path}")
    for writer in sources:
        mine = [r for r in rows if r["writer"] == writer]
        n_pass = sum(str(r["passed"]) == "True" for r in mine)
        drift = [r["problem_id"] for r in mine if str(r["grader_agrees"]) == "False"]
        print(f"  {writer}: {n_pass}/{len(mine)} passing" + (f"; disagrees with paper on {drift}" if drift else ""))


if __name__ == "__main__":
    main()
