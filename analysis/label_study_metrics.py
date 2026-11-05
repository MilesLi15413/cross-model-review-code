"""Summarize the authorship-label study per reviewer x writer family x arm."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.statistical_tests import benjamini_hochberg, mcnemar_test

SKIP_NAMES = {"run_meta.json", "preflight.json", "index.json", "report.json"}
BINARY_METRICS = ("unchanged", "fix", "regression")


def load_records(checkpoint_dir: str) -> List[Dict[str, object]]:
    records = []
    for path in sorted(Path(checkpoint_dir).glob("*/*.json")):
        if path.name not in SKIP_NAMES:
            records.append(json.loads(path.read_text()))
    return records


def label_condition(extra: Dict[str, object]) -> str:
    """`true`, `none`, or `false_<model named>`, so the two false labels stay separate."""

    arm = str(extra["label_arm"])
    return f"false_{extra['labeled_family']}" if arm == "false" else arm


def with_label_condition(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    for record in records:
        record["extra"]["label_condition"] = label_condition(record["extra"])
    return records


def is_valid(record: Dict[str, object]) -> bool:
    return not (record.get("cli_error") or record.get("timed_out") or record.get("parse_failed")) and (
        record.get("passed") is not None
    )


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def _mean(values: List[float]) -> Optional[float]:
    return round(mean(values), 4) if values else None


def _difference(left: Optional[float], right: Optional[float]) -> Optional[float]:
    return None if left is None or right is None else round(left - right, 4)


def summarize_group(records: List[Dict[str, object]]) -> Dict[str, object]:
    valid = [record for record in records if is_valid(record)]
    failing = [record for record in valid if not record["writer_passed"]]
    passing = [record for record in valid if record["writer_passed"]]
    issue_counts = [
        record["extra"]["issue_count"]
        for record in valid
        if record["extra"].get("issue_count") is not None
    ]
    return {
        "n": len(records),
        "n_valid": len(valid),
        "n_invalid": len(records) - len(valid),
        "unchanged_rate": _rate(sum(1 for r in valid if r["extra"].get("draft_unchanged")), len(valid)),
        "mean_diff_lines": _mean([r["extra"].get("diff_lines", 0) for r in valid]),
        "mean_issue_count": _mean(issue_counts),
        "n_issue_lists_missing": len(valid) - len(issue_counts),
        "n_failing_drafts": len(failing),
        "fix_rate": _rate(sum(1 for r in failing if r["passed"]), len(failing)),
        "n_passing_drafts": len(passing),
        "regression_rate": _rate(sum(1 for r in passing if not r["passed"]), len(passing)),
    }


def compute_summary(records: List[Dict[str, object]], group_key: str) -> List[Dict[str, object]]:
    """Group by reviewer, writer and `group_key`, comparing each group with the `none` group."""

    groups: Dict[Tuple[str, str, str], List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        extra = record["extra"]
        groups[(extra["reviewer_family"], extra["writer_family"], extra[group_key])].append(record)

    rows = []
    for (reviewer, writer, group), members in sorted(groups.items()):
        row = {"reviewer_family": reviewer, "writer_family": writer, group_key: group}
        row.update(summarize_group(members))
        baseline = summarize_group(groups.get((reviewer, writer, "none"), []))
        for metric in ("unchanged_rate", "mean_diff_lines", "mean_issue_count", "fix_rate", "regression_rate"):
            row[f"{metric}_vs_none"] = _difference(row[metric], baseline[metric])
        rows.append(row)
    return rows


def _metric_value(record: Dict[str, object], metric: str) -> Optional[bool]:
    if metric == "unchanged":
        return bool(record["extra"].get("draft_unchanged"))
    if metric == "fix":
        return None if record["writer_passed"] else bool(record["passed"])
    return None if not record["writer_passed"] else not record["passed"]


def compute_paired_tests(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Paired McNemar tests of each label (each false label separately) against `none` on the same drafts."""

    by_cell: Dict[Tuple[str, str, str], Dict[str, Dict[str, object]]] = defaultdict(dict)
    for record in records:
        if is_valid(record):
            extra = record["extra"]
            by_cell[(extra["reviewer_family"], extra["writer_family"], label_condition(extra))][
                str(record["task_id"])
            ] = record

    rows = []
    for (reviewer, writer, arm), arm_records in sorted(by_cell.items()):
        if arm == "none":
            continue
        baseline = by_cell.get((reviewer, writer, "none"), {})
        for metric in BINARY_METRICS:
            left, right = [], []
            for task_id in sorted(set(arm_records) & set(baseline)):
                arm_value = _metric_value(arm_records[task_id], metric)
                baseline_value = _metric_value(baseline[task_id], metric)
                if arm_value is not None and baseline_value is not None:
                    left.append(arm_value)
                    right.append(baseline_value)
            arm_only, none_only, statistic, p_value = mcnemar_test(left, right)
            rows.append(
                {
                    "reviewer_family": reviewer,
                    "writer_family": writer,
                    "label_condition": arm,
                    "metric": metric,
                    "n_pairs": len(left),
                    "arm_only": arm_only,
                    "none_only": none_only,
                    "mcnemar_chi2": statistic,
                    "p_value": p_value,
                }
            )

    for row, adjusted in zip(rows, benjamini_hochberg([row["p_value"] for row in rows])):
        row["p_adjusted_bh"] = adjusted
    return rows


def save_csv(rows: List[Dict[str, object]], path: str) -> None:
    if not rows:
        print(f"No rows for {path}")
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Label-study checkpoint directory")
    parser.add_argument("--output-prefix", default="results/processed/label_study")
    args = parser.parse_args()

    records = with_label_condition(load_records(args.input))
    if not records:
        raise SystemExit(f"No records found in {args.input}")
    save_csv(compute_summary(records, "label_arm"), f"{args.output_prefix}_summary.csv")
    save_csv(compute_summary(records, "label_condition"), f"{args.output_prefix}_by_false_label.csv")
    save_csv(compute_summary(records, "label_relation"), f"{args.output_prefix}_self_vs_other.csv")
    save_csv(compute_paired_tests(records), f"{args.output_prefix}_paired_tests.csv")


if __name__ == "__main__":
    main()
