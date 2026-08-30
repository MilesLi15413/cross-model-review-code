"""Evaluate completed LiveCodeBench records one at a time."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.lcb_eval_runner import SKIP_NAMES, evaluate_record
from analysis.result_index import write_run_index, write_tasks_csv
from experiments.run_experiment import merge_configs
from harness.core.parser import normalize_code_artifact
from harness.core.tracker import CostTracker, TaskRecord


def _evaluate_one(
    record: TaskRecord,
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
) -> tuple[Optional[bool], Optional[str], float]:
    return evaluate_record(record, config_path, benchmark_config_path, wall_timeout_s)


def _iter_condition_dirs(root: Path, condition: Optional[str]) -> list[Path]:
    condition_dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if condition:
        condition_dirs = [p for p in condition_dirs if p.name == condition]
    return condition_dirs


def _should_evaluate(
    record: TaskRecord,
    task_id: Optional[str],
    rerun: bool,
    include_cli_error_artifacts: bool,
    only_problematic: bool,
) -> bool:
    if task_id and record.task_id != task_id:
        return False
    if record.timed_out:
        return False
    if record.cli_error and not include_cli_error_artifacts:
        return False
    if not (record.final_artifact or "").strip():
        return False
    has_eval_error = bool(record.extra.get("lcb_eval_error"))
    artifact_was_fenced = normalize_code_artifact(record.final_artifact or "") != (record.final_artifact or "").strip()
    is_problematic = has_eval_error or artifact_was_fenced or bool(record.cli_error)
    if only_problematic and not is_problematic:
        return False
    if record.passed is not None and not rerun and not is_problematic:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate already-completed LiveCodeBench records without calling model CLIs. "
            "Each record is evaluated in its own process."
        )
    )
    parser.add_argument("--input", required=True, help="Raw checkpoint directory")
    parser.add_argument("--config", default="experiments/configs/all_conditions.yaml")
    parser.add_argument("--benchmark-config", default="experiments/configs/livecodebench.yaml")
    parser.add_argument("--condition", help="Evaluate only one condition directory")
    parser.add_argument("--task", help="Evaluate only one task id")
    parser.add_argument(
        "--wall-timeout-s",
        type=int,
        default=0,
        help="Optional per-record wall timeout. Use 0 for no wrapper timeout.",
    )
    parser.add_argument("--rerun", action="store_true", help="Re-evaluate records that already have passed set")
    parser.add_argument(
        "--include-cli-error-artifacts",
        action="store_true",
        help="Evaluate cli_error records when they still contain a final_artifact.",
    )
    parser.add_argument(
        "--only-problematic",
        action="store_true",
        help="Evaluate only records with lcb_eval_error, fenced artifacts, or included cli_error artifacts.",
    )
    parser.add_argument("--limit", type=int, help="Stop after evaluating this many records")
    parser.add_argument("--no-index", action="store_true", help="Do not refresh index/task CSV after evaluation")
    args = parser.parse_args()

    root = Path(args.input)
    if not root.exists():
        raise SystemExit(f"Input checkpoint does not exist: {root}")

    tracker = CostTracker(pricing_path=merge_configs(args.config, "livecodebench", args.benchmark_config)["pricing_path"])
    evaluated_count = 0
    timeout_count = 0
    error_count = 0

    for cond_dir in _iter_condition_dirs(root, args.condition):
        records = tracker.load_all(str(cond_dir))
        pending = [
            record
            for record in records
            if _should_evaluate(
                record,
                args.task,
                args.rerun,
                args.include_cli_error_artifacts,
                args.only_problematic,
            )
        ]
        print(f"{cond_dir.name}: {len(pending)} completed records pending evaluation", flush=True)

        for index, record in enumerate(pending, start=1):
            print(f"  [{index}/{len(pending)}] evaluating {record.task_id}...", end="", flush=True)
            passed, error, elapsed = _evaluate_one(
                record=record,
                config_path=args.config,
                benchmark_config_path=args.benchmark_config,
                wall_timeout_s=args.wall_timeout_s,
            )

            if error:
                record.passed = None
                record.extra["lcb_eval_error"] = error
                if "timeout" in error:
                    timeout_count += 1
                else:
                    error_count += 1
                print(f" {error} ({elapsed:.1f}s)", flush=True)
            else:
                record.passed = passed
                record.extra.pop("lcb_eval_error", None)
                evaluated_count += 1
                print(f" {'PASS' if passed else 'FAIL'} ({elapsed:.1f}s)", flush=True)

            tracker.save(record, str(cond_dir))

            if args.limit and evaluated_count >= args.limit:
                print(f"Stopped after --limit {args.limit}", flush=True)
                break

        if args.limit and evaluated_count >= args.limit:
            break

    if not args.no_index:
        write_run_index(str(root))
        write_tasks_csv(str(root))

    print(
        f"Done. evaluated={evaluated_count} eval_timeouts={timeout_count} eval_errors={error_count}",
        flush=True,
    )


if __name__ == "__main__":
    main()
