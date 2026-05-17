"""Inspect benchmark checkpoints without opening raw JSON files by hand."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.result_index import (
    build_run_index,
    load_record_entries,
    write_run_index,
    write_tasks_csv,
)


def _format_passed(value) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "PENDING"


def _print_run_summary(index: dict) -> None:
    print(f"Checkpoint: {index['checkpoint_dir']}")
    print(f"Benchmark:  {index.get('benchmark') or 'unknown'}")
    print(f"Tasks file: {index.get('tasks') or 'unknown'}")
    print(f"Records:    {index['records']} across {len(index['conditions'])} conditions")
    print(f"Updated:    {index.get('updated_at') or 'unknown'}")
    print()
    print(f"{'Condition':<38} {'Done':>5} {'Eval':>5} {'Pass':>5} {'ParseF':>6} {'Err':>4} {'TO':>3} {'Cost':>9}")
    print("-" * 86)
    for condition in index["conditions"]:
        print(
            f"{condition['condition']:<38} "
            f"{condition['completed']:>5} "
            f"{condition['evaluated']:>5} "
            f"{condition['passed']:>5} "
            f"{condition['parse_failed']:>6} "
            f"{condition['cli_error']:>4} "
            f"{condition['timed_out']:>3} "
            f"{condition['total_cost_usd']:>9.4f}"
        )


def _filtered_records(input_dir: str, condition: str | None, task_id: str | None):
    entries = []
    for file_path, record in load_record_entries(input_dir):
        if condition and record.get("condition") != condition:
            continue
        if task_id and record.get("task_id") != task_id:
            continue
        entries.append((file_path, record))
    return entries


def _print_records(input_dir: str, condition: str | None, task_id: str | None, show_artifact: bool) -> None:
    entries = _filtered_records(input_dir, condition, task_id)
    if not entries:
        print("No matching task records found.")
        return

    print()
    print(f"{'Task':<18} {'Condition':<38} {'Result':<8} {'Cost':>8} {'Latency':>8} {'Raw File'}")
    print("-" * 110)
    root = Path(input_dir)
    for file_path, record in entries:
        raw_file = str(file_path.relative_to(root)) if file_path.is_relative_to(root) else str(file_path)
        print(
            f"{str(record.get('task_id')):<18} "
            f"{str(record.get('condition')):<38} "
            f"{_format_passed(record.get('passed')):<8} "
            f"{float(record.get('total_cost_usd', 0.0) or 0.0):>8.4f} "
            f"{float(record.get('total_latency_s', 0.0) or 0.0):>8.1f} "
            f"{raw_file}"
        )
        if show_artifact:
            print("\n--- final_artifact ---")
            print(record.get("final_artifact", ""))
            print("--- end ---\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse raw benchmark checkpoint results")
    parser.add_argument("--input", required=True, help="Raw checkpoint directory, e.g. results/raw/lcb_pilot")
    parser.add_argument("--condition", help="Only show one condition")
    parser.add_argument("--task", help="Only show one task ID across conditions")
    parser.add_argument("--artifact", action="store_true", help="Print matching final_artifact content")
    parser.add_argument("--json", action="store_true", help="Print the run index JSON")
    parser.add_argument("--no-write", action="store_true", help="Do not refresh index.json or tasks.csv")
    args = parser.parse_args()

    if not args.no_write:
        index_path = write_run_index(args.input)
        tasks_path = write_tasks_csv(args.input)
    else:
        index_path = Path(args.input) / "index.json"
        tasks_path = None

    index = build_run_index(args.input)
    if args.json:
        print(json.dumps(index, indent=2))
    else:
        _print_run_summary(index)
        if args.condition or args.task:
            _print_records(args.input, args.condition, args.task, args.artifact)

    if not args.no_write:
        print()
        print(f"Index written: {index_path}")
        print(f"Task table:    {tasks_path}")


if __name__ == "__main__":
    main()
