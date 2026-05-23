"""Main experiment runner for the pair-programming benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
import math
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Dict, List, Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.core.cli_runner import CLIRunner, UsageLimitError
from harness.core.pipeline import TwoPassPipeline
from harness.core.preflight import build_preflight_runners, run_preflight
from harness.core.tracker import CostTracker
from analysis.result_index import write_run_index, write_tasks_csv


MIN_PYTHON = (3, 10)


def assert_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        found = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(
            f"Python {required}+ is required for this harness. Found {found}."
        )


def load_yaml(path: str) -> Dict[str, object]:
    return yaml.safe_load(Path(path).read_text()) or {}


def resolve_benchmark_config_path(benchmark: str, override: Optional[str] = None) -> str:
    if override:
        return override
    return str(Path("experiments/configs") / f"{benchmark}.yaml")


def merge_configs(shared_config_path: str, benchmark: str, benchmark_config_path: Optional[str] = None) -> Dict[str, object]:
    shared = load_yaml(shared_config_path)
    benchmark_path = resolve_benchmark_config_path(benchmark, benchmark_config_path)
    benchmark_config = load_yaml(benchmark_path)

    merged = dict(shared)
    merged["benchmark_config"] = benchmark_config.get("benchmark_config", {})
    merged["benchmark_config_path"] = benchmark_path
    if "pricing_path" not in merged:
        merged["pricing_path"] = "experiments/configs/pricing.yaml"
    return merged


def load_task_ids(path: str) -> List[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


DEFAULT_TASK_FILE_BY_BENCHMARK = {
    "livecodebench": "experiments/configs/lcb_100.txt",
    "swebench": "experiments/configs/sweb_50.txt",
}

DEFAULT_TASK_COUNT_BY_BENCHMARK = {
    "livecodebench": 100,
    "swebench": 50,
}


def infer_lcb_difficulty(tasks_path: str) -> Optional[str]:
    stem = Path(tasks_path).stem.lower()
    for difficulty in ("hard", "medium", "easy"):
        if re.search(rf"(^|[_-]){difficulty}([_-]|$)", stem):
            return difficulty
    return None


def resolve_tasks_path(benchmark: str, tasks_path: Optional[str], lcb_difficulty: Optional[str] = None) -> str:
    if tasks_path:
        return tasks_path
    if benchmark == "livecodebench" and lcb_difficulty:
        return str(Path("experiments/configs") / f"lcb_{lcb_difficulty}_100.txt")
    default_path = DEFAULT_TASK_FILE_BY_BENCHMARK.get(benchmark)
    if not default_path:
        raise SystemExit(f"No default task file configured for benchmark '{benchmark}'.")
    return default_path


def infer_task_count(output_path: str, benchmark: str) -> int:
    matches = re.findall(r"(\d+)", Path(output_path).stem)
    if matches:
        return int(matches[-1])
    return DEFAULT_TASK_COUNT_BY_BENCHMARK[benchmark]


def ensure_task_file(
    benchmark: str,
    benchmark_config: Dict[str, object],
    tasks_path: str,
    lcb_difficulty: Optional[str] = None,
) -> str:
    task_file = Path(tasks_path)
    if task_file.exists():
        print(f"Using task file: {task_file}")
        return str(task_file)

    total = infer_task_count(tasks_path, benchmark)
    inferred_lcb_difficulty = lcb_difficulty or infer_lcb_difficulty(tasks_path)
    difficulty_text = (
        f" difficulty={inferred_lcb_difficulty}" if benchmark == "livecodebench" and inferred_lcb_difficulty else ""
    )
    print(f"Task file {task_file} not found. Sampling {total} tasks for {benchmark}{difficulty_text}...")

    if benchmark == "livecodebench":
        from harness.benchmarks.livecodebench.task_sampler import sample_tasks

        sample_tasks(
            str(benchmark_config.get("dataset_path", "")),
            str(task_file),
            total=total,
            release_version=str(benchmark_config.get("release_version", "release_latest")),
            difficulty=inferred_lcb_difficulty,
        )
        return str(task_file)

    if benchmark == "swebench":
        from harness.benchmarks.swebench.task_sampler import sample_tasks

        sample_tasks(
            str(benchmark_config.get("dataset_path", "")),
            output_path=str(task_file),
            total=total,
            dataset_name=str(benchmark_config.get("dataset_name", "princeton-nlp/SWE-bench_Verified")),
            split=str(benchmark_config.get("split", "test")),
        )
        return str(task_file)

    raise SystemExit(f"Automatic task sampling is not supported for benchmark '{benchmark}'.")

def build_pipeline(
    condition: Dict[str, object],
    tracker: CostTracker,
    checkpoint_dir: str,
    status_callback=None,
) -> TwoPassPipeline:
    cond_checkpoint = os.path.join(checkpoint_dir, condition["id"])
    paused_sentinel = os.path.join(cond_checkpoint, "PAUSED")

    writer_cfg = condition["writer"]
    writer = CLIRunner(
        cli=writer_cfg["cli"],
        model=writer_cfg["model"],
        effort=writer_cfg.get("effort"),
        timeout_s=writer_cfg.get("timeout_s", 300),
        paused_sentinel_path=paused_sentinel,
        status_callback=status_callback,
    )

    reviewer_cfg = condition.get("reviewer")
    reviewer = None
    if reviewer_cfg:
        reviewer = CLIRunner(
            cli=reviewer_cfg["cli"],
            model=reviewer_cfg["model"],
            effort=reviewer_cfg.get("effort"),
            timeout_s=reviewer_cfg.get("timeout_s", 300),
            paused_sentinel_path=paused_sentinel,
            status_callback=status_callback,
        )

    return TwoPassPipeline(
        writer=writer,
        reviewer=reviewer,
        tracker=tracker,
        condition_id=condition["id"],
        per_task_budget_usd=condition.get("per_task_budget_usd", 10.0),
    )


def get_adapter(benchmark: str, config: Dict[str, object]):
    benchmark_config = config.get("benchmark_config", {})
    if benchmark == "livecodebench":
        from harness.benchmarks.livecodebench.adapter import LiveCodeBenchAdapter

        return LiveCodeBenchAdapter(**benchmark_config)
    if benchmark == "swebench":
        from harness.benchmarks.swebench.adapter import SWEBenchAdapter

        return SWEBenchAdapter(**benchmark_config)
    raise ValueError(f"Unknown benchmark: {benchmark}")


def check_paused(checkpoint_dir: str) -> List[Dict[str, object]]:
    """Return a list of PAUSED sentinel payloads found (per-condition or legacy root)."""
    found = []
    root_sentinel = Path(checkpoint_dir) / "PAUSED"
    if root_sentinel.exists():
        found.append(json.loads(root_sentinel.read_text()))
    for cond_dir in sorted(Path(checkpoint_dir).iterdir()):
        if cond_dir.is_dir():
            sentinel = cond_dir / "PAUSED"
            if sentinel.exists():
                found.append(json.loads(sentinel.read_text()))
    return found


def _safe_unlink(path: Path) -> None:
    if path.exists():
        path.unlink()


def _clear_paused_sentinels(checkpoint_dir: str) -> None:
    _safe_unlink(Path(checkpoint_dir) / "PAUSED")
    for cond_dir in Path(checkpoint_dir).iterdir():
        if cond_dir.is_dir():
            _safe_unlink(cond_dir / "PAUSED")


def _confirm_resume(checkpoint_dir: str, paused_list: List[Dict[str, object]], confirm_resume: bool) -> None:
    if not paused_list:
        return

    if confirm_resume:
        _clear_paused_sentinels(checkpoint_dir)
        return

    lines = "\n".join(
        f"  Condition: {p.get('blocked_condition')} | "
        f"Last task: {p.get('last_task_id')} | "
        f"CLI/model: {p.get('cli')}/{p.get('model')} | "
        f"Timestamp: {p.get('timestamp')}"
        for p in paused_list
    )
    summary = f"Paused run detected.\n{lines}\n"

    if not sys.stdin.isatty():
        raise SystemExit(summary + "Re-run with --confirm-resume once you are ready to continue.")

    print(summary)
    answer = input("Continue this paused run? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Resume cancelled by user.")
    _clear_paused_sentinels(checkpoint_dir)


def save_run_meta(
    checkpoint_dir: str,
    benchmark: str,
    config_path: str,
    benchmark_config_path: str,
    tasks_path: str,
    skip_eval: bool,
    skip_preflight: bool,
    lcb_difficulty: Optional[str] = None,
    conditions: Optional[List[Dict[str, object]]] = None,
) -> None:
    meta = {
        "benchmark": benchmark,
        "config": config_path,
        "benchmark_config_path": benchmark_config_path,
        "tasks": tasks_path,
        "skip_eval": skip_eval,
        "skip_preflight": skip_preflight,
        "lcb_difficulty": lcb_difficulty,
    }
    if conditions is not None:
        meta["conditions"] = [
            {
                "id": condition["id"],
                "writer": {
                    "cli": condition["writer"]["cli"],
                    "model": condition["writer"]["model"],
                    "effort": condition["writer"].get("effort"),
                },
                "reviewer": (
                    {
                        "cli": condition["reviewer"]["cli"],
                        "model": condition["reviewer"]["model"],
                        "effort": condition["reviewer"].get("effort"),
                    }
                    if condition.get("reviewer")
                    else None
                ),
            }
            for condition in conditions
        ]
    meta_path = Path(checkpoint_dir) / "run_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def _preflight_report_has_effort(report: Dict[str, object]) -> bool:
    checks = report.get("checks", [])
    return bool(checks) and all("effort" in check for check in checks if isinstance(check, dict))


def maybe_run_preflight(checkpoint_dir: str, conditions: List[dict], skip_preflight: bool) -> Dict[str, object]:
    preflight_path = Path(checkpoint_dir) / "preflight.json"
    if skip_preflight:
        print("Skipping CLI preflight.")
        return json.loads(preflight_path.read_text()) if preflight_path.exists() else {}

    if preflight_path.exists():
        cached = json.loads(preflight_path.read_text())
        if _preflight_report_has_effort(cached):
            print(f"Using cached preflight: {preflight_path}")
            return cached
        print(f"Refreshing stale preflight without effort metadata: {preflight_path}")

    print("Running CLI preflight checks...")
    runners = build_preflight_runners(
        conditions,
        paused_sentinel_path=str(Path(checkpoint_dir) / "PAUSED"),
    )
    report = run_preflight(runners, str(preflight_path))
    checks = report.get("checks", [])
    print(f"Preflight complete: {len(checks)} CLI/model/effort checks passed.")
    return report


def _per_task_evaluate(adapter, task, final_artifact: str) -> Optional[bool]:
    if hasattr(adapter, "evaluate_task"):
        return adapter.evaluate_task(task, final_artifact)
    return adapter.evaluate(task.task_id, final_artifact)


def _run_condition_batch_eval(adapter, tracker: CostTracker, checkpoint_dir: str) -> None:
    if not hasattr(adapter, "evaluate_batch"):
        return
    records = tracker.load_all(checkpoint_dir)
    if not records:
        return
    results = adapter.evaluate_batch(records)
    for record in records:
        if record.task_id in results:
            record.passed = results[record.task_id]
            tracker.save(record, checkpoint_dir)


def _format_eta(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        return "--:--"
    total_seconds = int(round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _compose_condition_status(restored: int, live_completed: int, detail: str = "") -> str:
    parts = []
    if restored:
        parts.append(f"restored {restored}")
    if live_completed:
        parts.append(f"live {live_completed}")
    if detail:
        parts.append(detail)
    return " | ".join(parts)


def run_with_rich(task_ids, conditions, adapter, tracker, checkpoint_dir, skip_eval, max_workers=None):
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    console = Console()
    total_tasks = len(task_ids) * len(conditions)
    uses_batch_eval = hasattr(adapter, "evaluate_batch")
    start_time = time.monotonic()

    console.print(
        f"[bold]Preparing run[/bold] | benchmark={task_ids and adapter.__class__.__name__ or 'unknown'} "
        f"| tasks={len(task_ids)} | conditions={len(conditions)} | checkpoint={checkpoint_dir}"
    )
    console.print("Loading benchmark tasks...")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description:<32}"),
        BarColumn(bar_width=20),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("[dim]{task.fields[status]}"),
        refresh_per_second=2,
        console=console,
    )

    cond_tasks = {
        cond["id"]: progress.add_task(cond["id"], total=len(task_ids), status="")
        for cond in conditions
    }
    overall_task = progress.add_task("[bold green]Overall", total=total_tasks, status="")

    cost_lock = threading.Lock()
    status_lock = threading.Lock()
    cost_total = 0.0
    restored_counts = {cond["id"]: 0 for cond in conditions}
    live_completed_counts = {cond["id"]: 0 for cond in conditions}
    runtime_status = {cond["id"]: "" for cond in conditions}
    total_restored = 0

    benchmark_tasks = adapter.load_tasks(task_ids)
    console.print(f"Loaded {len(benchmark_tasks)} tasks. Building work queue...")
    cond_by_id = {cond["id"]: cond for cond in conditions}
    cond_checkpoints = {cond["id"]: os.path.join(checkpoint_dir, cond["id"]) for cond in conditions}
    pending_jobs = []

    remaining_ids_by_condition = {}
    for cond in conditions:
        cond_checkpoint = cond_checkpoints[cond["id"]]
        os.makedirs(cond_checkpoint, exist_ok=True)
        remaining_ids = set()
        for task in benchmark_tasks:
            if tracker.is_done(task.task_id, cond["id"], cond_checkpoint):
                restored_counts[cond["id"]] += 1
                total_restored += 1
                progress.advance(cond_tasks[cond["id"]])
                progress.advance(overall_task)
                continue
            remaining_ids.add(task.task_id)
        remaining_ids_by_condition[cond["id"]] = remaining_ids
        progress.update(
            cond_tasks[cond["id"]],
            status=_compose_condition_status(restored_counts[cond["id"]], 0),
        )
        if not remaining_ids and not (not skip_eval and uses_batch_eval):
            progress.update(cond_tasks[cond["id"]], status="[green]done")

    for task in benchmark_tasks:
        for cond in conditions:
            if task.task_id in remaining_ids_by_condition[cond["id"]]:
                pending_jobs.append((cond["id"], task))

    if total_restored:
        console.print(f"Restored {total_restored} completed task-condition records from checkpoint.")
        for cond in conditions:
            restored = restored_counts[cond["id"]]
            if restored:
                console.print(f"  {cond['id']}: restored {restored}/{len(task_ids)} from checkpoint")

    console.print(
        f"Queue ready: {len(pending_jobs)} remaining task-condition jobs "
        f"across {min(len(pending_jobs), max_workers or len(conditions)) or 1} workers."
    )

    stop_event = threading.Event()

    def make_status_callback(cond_id: str):
        def _callback(event: Dict[str, object]) -> None:
            if event.get("event") == "rate_limit_wait":
                with status_lock:
                    runtime_status[cond_id] = (
                        f"waiting {event['cli']} limit "
                        f"retry #{event['retry_number']} in {event['delay_s']}s"
                    )
        return _callback

    def run_job(cond_id: str, task):
        if stop_event.is_set():
            return {"cond_id": cond_id, "task_id": task.task_id, "skipped": True}

        with status_lock:
            runtime_status[cond_id] = f"running {task.task_id[:18]}"

        pipeline = build_pipeline(
            cond_by_id[cond_id],
            tracker,
            checkpoint_dir,
            status_callback=make_status_callback(cond_id),
        )
        result = pipeline.run_task(task)
        if not skip_eval and not uses_batch_eval and not result.record.cli_error:
            result.record.passed = _per_task_evaluate(adapter, task, result.final_artifact)
        tracker.save(result.record, cond_checkpoints[cond_id])
        return {
            "cond_id": cond_id,
            "task_id": task.task_id,
            "record": result.record,
        }

    workers = min(len(pending_jobs), max_workers or len(conditions)) or 1
    with progress:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {}
            for cond_id, task in pending_jobs:
                progress.update(
                    cond_tasks[cond_id],
                    status=_compose_condition_status(
                        restored_counts[cond_id],
                        live_completed_counts[cond_id],
                        f"queued {task.task_id[:18]}",
                    ),
                )
                future = pool.submit(run_job, cond_id, task)
                future_map[future] = (cond_id, task.task_id)

            while future_map:
                done, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED, timeout=0.25)
                elapsed = max(time.monotonic() - start_time, 0.001)
                completed = progress.tasks[overall_task].completed
                remaining = max(total_tasks - completed, 0)
                rate = completed / elapsed if completed else 0.0
                eta = _format_eta(remaining / rate) if rate else "--:--"
                with cost_lock:
                    progress.update(
                        overall_task,
                        status=(
                            f"ETA {eta} | ${cost_total:.3f} | {len(future_map)} running "
                            f"| restored {total_restored}"
                        ),
                    )
                with status_lock:
                    status_snapshot = dict(runtime_status)
                for cond in conditions:
                    cond_id = cond["id"]
                    detail = status_snapshot.get(cond_id, "")
                    if detail and not progress.tasks[cond_tasks[cond_id]].finished:
                        progress.update(
                            cond_tasks[cond_id],
                            status=_compose_condition_status(
                                restored_counts[cond_id],
                                live_completed_counts[cond_id],
                                detail,
                            ),
                        )

                for future in done:
                    cond_id, task_id = future_map.pop(future)
                    try:
                        payload = future.result()
                    except UsageLimitError:
                        stop_event.set()
                        progress.update(cond_tasks[cond_id], status="[red]manual pause")
                        raise
                    except Exception as exc:
                        stop_event.set()
                        progress.update(cond_tasks[cond_id], status=f"[red]error {task_id[:12]}")
                        raise exc

                    if payload.get("skipped"):
                        continue

                    record = payload["record"]
                    live_completed_counts[cond_id] += 1
                    with status_lock:
                        runtime_status[cond_id] = ""
                    with cost_lock:
                        cost_total += record.total_cost_usd
                    icon = "⚠" if record.cli_error else "✓"
                    progress.update(
                        cond_tasks[cond_id],
                        advance=1,
                        status=_compose_condition_status(
                            restored_counts[cond_id],
                            live_completed_counts[cond_id],
                            f"{icon} {task_id[:18]}",
                        ),
                    )
                    progress.advance(overall_task)

            if not skip_eval and uses_batch_eval:
                console.print("Inference complete. Running batch evaluation...")
                for cond in conditions:
                    cond_checkpoint = cond_checkpoints[cond["id"]]
                    progress.update(cond_tasks[cond["id"]], status="[yellow]batch eval")
                    console.print(f"  Evaluating {cond['id']}...")
                    _run_condition_batch_eval(adapter, tracker, cond_checkpoint)
                    write_run_index(checkpoint_dir)
                    progress.update(cond_tasks[cond["id"]], status="[green]done")
            else:
                for cond in conditions:
                    progress.update(cond_tasks[cond["id"]], status="[green]done")

    with cost_lock:
        write_run_index(checkpoint_dir)
        write_tasks_csv(checkpoint_dir)
        console.print(f"\n[bold green]Done.[/bold green] Total cost: ${cost_total:.3f}")


def run_plain(task_ids, conditions, adapter, tracker, checkpoint_dir, skip_eval):
    uses_batch_eval = hasattr(adapter, "evaluate_batch")
    print("Loading benchmark tasks...")
    benchmark_tasks = adapter.load_tasks(task_ids)
    print(f"Loaded {len(benchmark_tasks)} tasks.")

    print(
        f"{'=' * 60}\n"
        f"  LLM Pair Benchmark\n"
        f"  Tasks: {len(task_ids)} | Conditions: {len(conditions)}\n"
        f"{'=' * 60}"
    )

    total_cost = 0.0
    for cond in conditions:
        cond_checkpoint = os.path.join(checkpoint_dir, cond["id"])
        os.makedirs(cond_checkpoint, exist_ok=True)
        pipeline = build_pipeline(cond, tracker, checkpoint_dir)
        print(f"\n[{cond['id']}] Starting {len(task_ids)} tasks...")

        for index, task in enumerate(benchmark_tasks, start=1):
            if tracker.is_done(task.task_id, cond["id"], cond_checkpoint):
                continue

            print(f"  [{cond['id']}] {index}/{len(task_ids)} {task.task_id} ... ", end="", flush=True)
            try:
                result = pipeline.run_task(task)
            except UsageLimitError:
                print("\nManual pause requested.")
                print(f"Resume with: python experiments/run_experiment.py --resume {checkpoint_dir}")
                return

            if not skip_eval and not uses_batch_eval and not result.record.cli_error:
                result.record.passed = _per_task_evaluate(adapter, task, result.final_artifact)

            tracker.save(result.record, cond_checkpoint)
            write_run_index(checkpoint_dir)
            total_cost += result.record.total_cost_usd
            print(f"${result.record.total_cost_usd:.3f}  {result.record.total_latency_s:.1f}s")

        if not skip_eval and uses_batch_eval:
            print(f"  [{cond['id']}] Running batch evaluation...")
            _run_condition_batch_eval(adapter, tracker, cond_checkpoint)
            write_run_index(checkpoint_dir)
            print(f"  [{cond['id']}] Batch evaluation complete.")

    write_run_index(checkpoint_dir)
    write_tasks_csv(checkpoint_dir)
    print(f"\n{'=' * 60}\nDone. Total cost: ${total_cost:.3f}\n{'=' * 60}")


def main():
    assert_supported_python()

    parser = argparse.ArgumentParser(description="LLM pair-programming benchmark runner")
    parser.add_argument("--benchmark", choices=["livecodebench", "swebench"])
    parser.add_argument(
        "--config",
        default="experiments/configs/all_conditions.yaml",
        help="Shared conditions YAML",
    )
    parser.add_argument("--benchmark-config", help="Optional benchmark-specific YAML override")
    parser.add_argument("--tasks", help="Text file with task IDs; auto-generated if missing")
    parser.add_argument("--checkpoint", help="Directory for per-task result files")
    parser.add_argument("--resume", metavar="CHECKPOINT_DIR", help="Resume a paused run")
    parser.add_argument("--confirm-resume", action="store_true", help="Skip the resume prompt")
    parser.add_argument("--skip-eval", action="store_true", help="Skip benchmark evaluation")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip live CLI smoke tests")
    parser.add_argument(
        "--lcb-difficulty",
        choices=["easy", "medium", "hard"],
        help="LiveCodeBench-only task difficulty filter for auto-generated task files",
    )
    parser.add_argument("--workers", type=int, default=None, metavar="N", help="Max parallel conditions (default: all)")
    args = parser.parse_args()

    if args.resume:
        checkpoint_dir = args.resume
        meta_path = Path(checkpoint_dir) / "run_meta.json"
        if not meta_path.exists():
            raise SystemExit("No run_meta.json found in resume directory.")

        meta = json.loads(meta_path.read_text())
        paused = check_paused(checkpoint_dir)
        _confirm_resume(checkpoint_dir, paused, args.confirm_resume)

        args.benchmark = meta["benchmark"]
        args.config = meta["config"]
        args.benchmark_config = meta.get("benchmark_config_path")
        args.tasks = meta["tasks"]
        args.checkpoint = checkpoint_dir
        args.skip_eval = meta.get("skip_eval", False)
        args.skip_preflight = meta.get("skip_preflight", False)
        args.lcb_difficulty = meta.get("lcb_difficulty")

    if not all([args.benchmark, args.checkpoint]):
        parser.error("--benchmark and --checkpoint are required (or use --resume)")
    if args.lcb_difficulty and args.benchmark != "livecodebench":
        parser.error("--lcb-difficulty is only supported for --benchmark livecodebench")

    os.makedirs(args.checkpoint, exist_ok=True)

    config = merge_configs(args.config, args.benchmark, args.benchmark_config)
    args.tasks = resolve_tasks_path(args.benchmark, args.tasks, args.lcb_difficulty)
    args.tasks = ensure_task_file(args.benchmark, config["benchmark_config"], args.tasks, args.lcb_difficulty)
    print(
        f"Starting benchmark run: benchmark={args.benchmark} "
        f"checkpoint={args.checkpoint} tasks={args.tasks}"
    )
    save_run_meta(
        checkpoint_dir=args.checkpoint,
        benchmark=args.benchmark,
        config_path=args.config,
        benchmark_config_path=config["benchmark_config_path"],
        tasks_path=args.tasks,
        skip_eval=args.skip_eval,
        skip_preflight=args.skip_preflight,
        lcb_difficulty=args.lcb_difficulty,
        conditions=config["conditions"],
    )
    write_run_index(args.checkpoint)

    task_ids = load_task_ids(args.tasks)
    conditions = config["conditions"]
    tracker = CostTracker(pricing_path=config["pricing_path"])
    adapter = get_adapter(args.benchmark, config)
    maybe_run_preflight(args.checkpoint, conditions, args.skip_preflight)

    try:
        import rich  # noqa: F401

        run_with_rich(task_ids, conditions, adapter, tracker, args.checkpoint, args.skip_eval, args.workers)
    except ImportError:
        run_plain(task_ids, conditions, adapter, tracker, args.checkpoint, args.skip_eval)


if __name__ == "__main__":
    main()
