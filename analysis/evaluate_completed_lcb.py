"""Evaluate completed LiveCodeBench records one at a time."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import queue
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.result_index import write_run_index, write_tasks_csv
from experiments.run_experiment import get_adapter, merge_configs
from harness.core.parser import normalize_code_artifact
from harness.core.tracker import CostTracker, TaskRecord


SKIP_NAMES = {"run_meta.json", "preflight.json", "index.json", "report.json"}


def _evaluate_one_worker(
    config_path: str,
    benchmark_config_path: str,
    record: TaskRecord,
    result_queue,
) -> None:
    config = merge_configs(config_path, "livecodebench", benchmark_config_path)
    config["benchmark_config"]["num_process_evaluate"] = 1
    adapter = get_adapter("livecodebench", config)
    record.final_artifact = normalize_code_artifact(record.final_artifact or "")
    result = adapter.evaluate_batch([record])
    result_queue.put(result.get(record.task_id))


def _evaluate_one(
    record: TaskRecord,
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
) -> tuple[Optional[bool], Optional[str], float]:
    started = time.monotonic()
    ctx = mp.get_context("fork")
    result_queue = ctx.Queue()
    proc = ctx.Process(
        target=_evaluate_one_worker,
        args=(config_path, benchmark_config_path, record, result_queue),
    )
    proc.start()
    timeout = wall_timeout_s if wall_timeout_s > 0 else None
    proc.join(timeout)
    elapsed = time.monotonic() - started

    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return None, f"lcb_eval_wall_timeout_after_{wall_timeout_s}s", elapsed

    if proc.exitcode != 0:
        return None, f"lcb_eval_process_exit_{proc.exitcode}", elapsed

    try:
        passed = result_queue.get_nowait()
    except queue.Empty:
        return None, "lcb_eval_returned_no_result", elapsed

    if passed is None:
        return None, "lcb_eval_returned_none", elapsed
    return bool(passed), None, elapsed


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
