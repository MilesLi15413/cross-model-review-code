"""Helpers for browsing and indexing raw benchmark checkpoints."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from harness.core.tracker import CostTracker, TaskRecord


METADATA_FILES = {"run_meta.json", "preflight.json", "report.json", "index.json"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _record_paths(checkpoint_dir: str) -> List[Path]:
    root = Path(checkpoint_dir)
    if not root.exists():
        return []
    paths = []
    for file_path in root.rglob("*.json"):
        if file_path.name in METADATA_FILES:
            continue
        paths.append(file_path)
    return sorted(paths)


def load_record_entries(checkpoint_dir: str) -> List[Tuple[Path, Dict[str, object]]]:
    entries: List[Tuple[Path, Dict[str, object]]] = []
    for file_path in _record_paths(checkpoint_dir):
        payload = json.loads(file_path.read_text())
        if "task_id" in payload and "condition" in payload:
            entries.append((file_path, payload))
    return entries


def _timestamp_bounds(entries: Iterable[Tuple[Path, Dict[str, object]]]) -> Tuple[Optional[str], Optional[str]]:
    starts: List[str] = []
    finishes: List[str] = []
    for file_path, record in entries:
        for key in ("writer_started_at", "reviewer_started_at"):
            value = str(record.get(key, "") or "")
            if value:
                starts.append(value)
        for key in ("writer_finished_at", "reviewer_finished_at"):
            value = str(record.get(key, "") or "")
            if value:
                finishes.append(value)
        if not starts:
            starts.append(datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).isoformat())
        finishes.append(datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).isoformat())
    return (min(starts) if starts else None, max(finishes) if finishes else None)


def build_run_index(checkpoint_dir: str) -> Dict[str, object]:
    root = Path(checkpoint_dir)
    entries = load_record_entries(checkpoint_dir)
    records = [record for _, record in entries]
    run_meta = _safe_json(root / "run_meta.json")
    preflight = _safe_json(root / "preflight.json")

    by_condition: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        by_condition[str(record["condition"])].append(record)

    for child in sorted(root.iterdir() if root.exists() else []):
        if child.is_dir():
            by_condition.setdefault(child.name, [])

    condition_summaries = []
    tracker = CostTracker()
    for condition_id in sorted(by_condition):
        condition_records = by_condition[condition_id]
        completed_records = [
            record
            for record in condition_records
            if tracker.record_is_complete(TaskRecord(**record))
        ]
        evaluated = [record for record in condition_records if record.get("passed") is not None]
        passed = sum(1 for record in evaluated if bool(record.get("passed")))
        total_cost = sum(float(record.get("total_cost_usd", 0.0) or 0.0) for record in condition_records)
        total_latency = sum(float(record.get("total_latency_s", 0.0) or 0.0) for record in condition_records)
        condition_summaries.append(
            {
                "condition": condition_id,
                "directory": str(root / condition_id),
                "completed": len(completed_records),
                "attempted": len(condition_records),
                "evaluated": len(evaluated),
                "passed": passed,
                "parse_failed": sum(1 for record in condition_records if record.get("parse_failed")),
                "cli_error": sum(1 for record in condition_records if record.get("cli_error")),
                "timed_out": sum(1 for record in condition_records if record.get("timed_out")),
                "total_cost_usd": round(total_cost, 6),
                "avg_total_latency_s": round(total_latency / len(condition_records), 2)
                if condition_records
                else 0.0,
            }
        )

    started_at, updated_at = _timestamp_bounds(entries)
    return {
        "checkpoint_dir": str(root),
        "generated_at": _now_iso(),
        "started_at": started_at,
        "updated_at": updated_at or _now_iso(),
        "benchmark": run_meta.get("benchmark"),
        "config": run_meta.get("config"),
        "benchmark_config_path": run_meta.get("benchmark_config_path"),
        "tasks": run_meta.get("tasks"),
        "condition_settings": run_meta.get("conditions", []),
        "preflight_checked_at": preflight.get("checked_at"),
        "records": len(records),
        "unique_tasks": len({record["task_id"] for record in records}),
        "conditions": condition_summaries,
    }


def write_run_index(checkpoint_dir: str) -> Path:
    output = Path(checkpoint_dir) / "index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_run_index(checkpoint_dir), indent=2))
    return output


def processed_dir_for(checkpoint_dir: str) -> Path:
    root = Path(checkpoint_dir)
    parts = root.parts
    if "raw" in parts:
        raw_index = parts.index("raw")
        tail = parts[raw_index + 1 :]
        if tail:
            return Path(*parts[:raw_index], "processed", *tail)
    return Path("results") / "processed" / root.name


TASK_TABLE_FIELDS = [
    "task_id",
    "condition",
    "benchmark",
    "passed",
    "writer_model",
    "reviewer_model",
    "writer_effort",
    "reviewer_effort",
    "total_cost_usd",
    "total_latency_s",
    "writer_latency_s",
    "reviewer_latency_s",
    "parse_failed",
    "cli_error",
    "timed_out",
    "budget_exceeded",
    "evaluated_turn",
    "evaluated_parse_method",
    "raw_file",
    "final_artifact",
]


def task_rows(checkpoint_dir: str) -> List[Dict[str, object]]:
    rows = []
    root = Path(checkpoint_dir)
    for file_path, record in load_record_entries(checkpoint_dir):
        rows.append(
            {
                "task_id": record.get("task_id"),
                "condition": record.get("condition"),
                "benchmark": record.get("benchmark"),
                "passed": record.get("passed"),
                "writer_model": record.get("writer_model"),
                "reviewer_model": record.get("reviewer_model"),
                "writer_effort": record.get("writer_effort"),
                "reviewer_effort": record.get("reviewer_effort"),
                "total_cost_usd": record.get("total_cost_usd", 0.0),
                "total_latency_s": record.get("total_latency_s", 0.0),
                "writer_latency_s": record.get("writer_latency_s", 0.0),
                "reviewer_latency_s": record.get("reviewer_latency_s", 0.0),
                "parse_failed": record.get("parse_failed", False),
                "cli_error": record.get("cli_error", False),
                "timed_out": record.get("timed_out", False),
                "budget_exceeded": record.get("budget_exceeded", False),
                "evaluated_turn": record.get("evaluated_turn", ""),
                "evaluated_parse_method": record.get("evaluated_parse_method", ""),
                "raw_file": str(file_path.relative_to(root)) if file_path.is_relative_to(root) else str(file_path),
                "final_artifact": record.get("final_artifact", ""),
            }
        )
    return sorted(rows, key=lambda row: (str(row["condition"]), str(row["task_id"])))


def write_tasks_csv(checkpoint_dir: str, output_path: Optional[str] = None) -> Path:
    output = Path(output_path) if output_path else processed_dir_for(checkpoint_dir) / "tasks.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = task_rows(checkpoint_dir)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TASK_TABLE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output
