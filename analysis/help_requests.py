"""Report help requests per model from a help-tracking checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.label_study_metrics import SKIP_NAMES, _rate, save_csv
from harness.core.parser import HELP_REQUEST_TYPES


def load_records(checkpoint_dir: str) -> List[Dict[str, object]]:
    records = []
    for path in sorted(Path(checkpoint_dir).glob("*/*.json")):
        if path.name not in SKIP_NAMES:
            records.append(json.loads(path.read_text()))
    return records


def _pass_rate(records: List[Dict[str, object]]) -> Optional[float]:
    graded = [record for record in records if record.get("passed") is not None]
    return _rate(sum(1 for record in graded if record["passed"]), len(graded))


def _has_type(record: Dict[str, object], request_type: str) -> bool:
    requests = record["extra"]["help_tracking"]["tagged_requests"]
    return any(request["type"] == request_type for request in requests)


def summarize_model(model: str, records: List[Dict[str, object]]) -> Dict[str, object]:
    tracked = [record for record in records if "help_tracking" in record.get("extra", {})]
    help_data = [record["extra"]["help_tracking"] for record in tracked]
    with_requests = [r for r in tracked if r["extra"]["help_tracking"]["tagged_count"] > 0]
    without_requests = [r for r in tracked if r["extra"]["help_tracking"]["tagged_count"] == 0]
    total = sum(item["tagged_count"] for item in help_data)
    row: Dict[str, object] = {
        "model": model,
        "tasks": len(records),
        "tasks_tracked": len(tracked),
        "invalid_calls": len(records) - len(tracked),
        "tagged_requests": total,
        "requests_per_task": _rate(total, len(tracked)),
        "pct_tasks_with_request": _rate(len(with_requests), len(tracked)),
    }
    for request_type in HELP_REQUEST_TYPES:
        row[f"type_{request_type}"] = sum(
            1
            for item in help_data
            for request in item["tagged_requests"]
            if request["type"] == request_type
        )
    row.update(
        {
            "pass_rate_with_requests": _pass_rate(with_requests),
            "pass_rate_without_requests": _pass_rate(without_requests),
            "tasks_no_code": sum(1 for item in help_data if item["no_code"]),
            "malformed_tags": sum(item["malformed_tags"] for item in help_data),
            "untagged_requests": sum(item["untagged_count"] for item in help_data),
            "pct_tasks_with_untagged": _rate(
                sum(1 for item in help_data if item["untagged_count"] > 0), len(tracked)
            ),
            "pass_rate_with_uncertainty": _pass_rate([r for r in tracked if _has_type(r, "uncertainty")]),
            "pass_rate_without_uncertainty": _pass_rate(
                [r for r in tracked if not _has_type(r, "uncertainty")]
            ),
        }
    )
    for label in ("high", "medium", "low"):
        members = [r for r in tracked if r.get("writer_confidence_label") == label]
        row[f"n_confidence_{label}"] = len(members)
        row[f"pass_rate_confidence_{label}"] = _pass_rate(members)
    row["n_confidence_missing"] = sum(
        1 for r in tracked if r.get("writer_confidence_label") not in ("high", "medium", "low")
    )
    return row


def detail_rows(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    rows = []
    for record in records:
        tracking = record.get("extra", {}).get("help_tracking")
        rows.append(
            {
                "model": record["writer_model"],
                "task_id": record["task_id"],
                "passed": record.get("passed"),
                "confidence_label": record.get("writer_confidence_label"),
                "tagged_count": tracking["tagged_count"] if tracking else None,
                "untagged_count": tracking["untagged_count"] if tracking else None,
                "no_code": tracking["no_code"] if tracking else None,
                "requests": json.dumps(tracking["tagged_requests"]) if tracking else "",
                "untagged_matches": json.dumps(tracking["untagged_matches"]) if tracking else "",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Help-tracking checkpoint directory")
    parser.add_argument("--output-prefix", default="results/processed/help_requests")
    args = parser.parse_args()

    records = load_records(args.input)
    if not records:
        raise SystemExit(f"No records found in {args.input}")
    by_model: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        by_model[str(record["writer_model"])].append(record)
    rows = [summarize_model(model, members) for model, members in sorted(by_model.items())]
    save_csv(rows, f"{args.output_prefix}_summary.csv")
    save_csv(detail_rows(records), f"{args.output_prefix}_detail.csv")


if __name__ == "__main__":
    main()
