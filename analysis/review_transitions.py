"""Same-candidate reviewer transitions from stored writer drafts.

`compute_metrics.py` compares a reviewed condition against an *independently
sampled* solo baseline. That is a contrast between two whole pipelines: the two arms
almost never share a draft, so it cannot say whether a reviewer fixed or broke the
program it was actually handed.

This module reports the other quantity. Once `evaluate_writer_artifacts.py` has
scored each record's stored draft, every reviewed record carries a before/after pair
on one fixed candidate, and reviewer fixes and regressions become directly
observable. Both quantities are emitted side by side so the difference between them
is visible rather than assumed.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.compute_metrics import filter_records, load_pooled_records


FIELDS = [
    "condition",
    "writer_model",
    "reviewer_model",
    "n_records",
    "n_scored",
    "n_unscorable",
    "unchanged_artifact",
    "kept_pass",
    "reviewer_fix",
    "reviewer_regression",
    "kept_fail",
    "writer_pass_rate",
    "final_pass_rate",
    "net_same_candidate_change",
    "cross_condition_fixes",
    "cross_condition_regressions",
]


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def compute_transitions(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    by_condition: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        by_condition[str(record["condition"])].append(record)

    baselines: Dict[str, str] = {}
    for condition_id, condition_records in by_condition.items():
        if condition_records and condition_records[0].get("reviewer_model") is None:
            baselines[str(condition_records[0]["writer_model"])] = condition_id

    rows: List[Dict[str, object]] = []
    for condition_id in sorted(by_condition):
        condition_records = by_condition[condition_id]
        writer_model = str(condition_records[0]["writer_model"])
        reviewer_model = condition_records[0].get("reviewer_model")
        if reviewer_model is None:
            continue

        scored = [
            record
            for record in condition_records
            if record.get("writer_passed") is not None and record.get("passed") is not None
        ]
        kept_pass = sum(1 for r in scored if r["writer_passed"] and r["passed"])
        reviewer_fix = sum(1 for r in scored if not r["writer_passed"] and r["passed"])
        reviewer_regression = sum(1 for r in scored if r["writer_passed"] and not r["passed"])
        kept_fail = sum(1 for r in scored if not r["writer_passed"] and not r["passed"])
        unchanged = sum(
            1
            for r in condition_records
            if (r.get("extra") or {}).get("reviewer_changed_artifact") is False
        )

        # The pipeline-level counterpart, for contrast: outcome flips against the
        # writer's separately sampled solo arm on the same tasks.
        baseline_condition = baselines.get(writer_model)
        cross_fixes = cross_regressions = None
        if baseline_condition:
            baseline_by_task = {
                str(record["task_id"]): record
                for record in by_condition[baseline_condition]
                if record.get("passed") is not None
            }
            cross_fixes = 0
            cross_regressions = 0
            for record in condition_records:
                baseline = baseline_by_task.get(str(record["task_id"]))
                if not baseline or record.get("passed") is None:
                    continue
                if not baseline["passed"] and record["passed"]:
                    cross_fixes += 1
                if baseline["passed"] and not record["passed"]:
                    cross_regressions += 1

        rows.append(
            {
                "condition": condition_id,
                "writer_model": writer_model,
                "reviewer_model": reviewer_model,
                "n_records": len(condition_records),
                "n_scored": len(scored),
                "n_unscorable": len(condition_records) - len(scored),
                "unchanged_artifact": unchanged,
                "kept_pass": kept_pass,
                "reviewer_fix": reviewer_fix,
                "reviewer_regression": reviewer_regression,
                "kept_fail": kept_fail,
                "writer_pass_rate": _rate(kept_pass + reviewer_regression, len(scored)),
                "final_pass_rate": _rate(kept_pass + reviewer_fix, len(scored)),
                "net_same_candidate_change": reviewer_fix - reviewer_regression,
                "cross_condition_fixes": cross_fixes,
                "cross_condition_regressions": cross_regressions,
            }
        )
    return rows


def print_report(rows: List[Dict[str, object]]) -> None:
    print(f"\n{'─' * 118}")
    print(
        f"{'Condition':<32} {'Scored':>7} {'Unsc':>5} {'Same':>5} {'KeptP':>6} {'Fix':>5} "
        f"{'Reg':>5} {'KeptF':>6} {'Net':>5} {'xFix':>5} {'xReg':>5}"
    )
    print(f"{'─' * 118}")
    for row in rows:
        print(
            f"{row['condition']:<32} {row['n_scored']:>7} {row['n_unscorable']:>5} "
            f"{row['unchanged_artifact']:>5} {row['kept_pass']:>6} {row['reviewer_fix']:>5} "
            f"{row['reviewer_regression']:>5} {row['kept_fail']:>6} "
            f"{row['net_same_candidate_change']:>+5} "
            f"{str(row['cross_condition_fixes']):>5} {str(row['cross_condition_regressions']):>5}"
        )
    print(f"{'─' * 118}")
    print(
        "Fix/Reg are same-candidate transitions on the draft the reviewer received; "
        "xFix/xReg are cross-condition\nflips against an independently sampled solo run "
        "of the same writer."
    )


def save_csv(rows: List[Dict[str, object]], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Transitions saved to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, nargs="+", help="One or more checkpoint dirs")
    parser.add_argument("--input-label", action="append", help="Slice label per --input, in order")
    parser.add_argument(
        "--analysis-set",
        choices=["all", "complete-case"],
        default="complete-case",
        help="Use all records or only tasks with valid answers for every condition",
    )
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--report", action="store_true", help="Print a summary table")
    args = parser.parse_args()

    records = load_pooled_records(args.input, args.input_label)
    records = filter_records(records, args.analysis_set)
    rows = compute_transitions(records)
    if not rows:
        print("No reviewed conditions found.")
        return
    if args.report or not args.output:
        print_report(rows)
    if args.output:
        save_csv(rows, args.output)


if __name__ == "__main__":
    main()
