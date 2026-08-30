"""Shared helpers for scoring stored artifacts with the LiveCodeBench evaluator.

Both `evaluate_completed_lcb.py` and `evaluate_writer_artifacts.py` re-score records
that already exist on disk, so the evaluation loop lives here to keep the two entry
points behaviourally identical.

Evaluation runs in a fresh interpreter (`_lcb_eval_child.py`), not a forked child.
LiveCodeBench executes candidate programs through its own multiprocessing pool; when
that pool is started inside a forked process it does not raise, it reports every
sample as failing. An earlier version of this harness forked, which silently scores
correct programs as failures.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.core.tracker import TaskRecord

CHILD_SCRIPT = Path(__file__).resolve().parent / "_lcb_eval_child.py"

SKIP_NAMES = {"run_meta.json", "preflight.json", "index.json", "report.json"}


def _run_child(
    items: List[Dict[str, str]],
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
    num_process_evaluate: Optional[int] = None,
) -> Tuple[Optional[Dict[str, bool]], Optional[str], float]:
    payload = {
        "config": config_path,
        "benchmark_config": benchmark_config_path,
        "items": items,
    }
    if num_process_evaluate:
        payload["num_process_evaluate"] = num_process_evaluate

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lcb_eval_") as tmp_dir:
        tmp = Path(tmp_dir)
        payload_path = tmp / "payload.json"
        output_path = tmp / "results.json"
        log_path = tmp / "child.log"
        payload_path.write_text(json.dumps(payload))

        # The child is started in its own session and its output goes to a file rather
        # than a pipe. LiveCodeBench's evaluator spawns its own worker processes; if we
        # killed only the direct child while holding a pipe open, surviving workers
        # would keep that pipe open and the timeout would never actually return.
        with log_path.open("w") as log_handle:
            proc = subprocess.Popen(
                [sys.executable, str(CHILD_SCRIPT), str(payload_path), str(output_path)],
                cwd=str(ROOT),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            timed_out = False
            try:
                proc.wait(timeout=wall_timeout_s if wall_timeout_s > 0 else None)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_group(proc)

        elapsed = time.monotonic() - started
        if timed_out:
            return None, f"lcb_eval_wall_timeout_after_{wall_timeout_s}s", elapsed

        if proc.returncode != 0:
            detail = log_path.read_text().strip().splitlines() if log_path.exists() else []
            tail = detail[-1] if detail else "no output"
            return None, f"lcb_eval_process_exit_{proc.returncode}: {tail}", elapsed

        if not output_path.exists():
            return None, "lcb_eval_returned_no_result", elapsed

        return json.loads(output_path.read_text()), None, elapsed


def _kill_process_group(proc: "subprocess.Popen") -> None:
    """Kill the child and any evaluator workers it started."""

    try:
        group = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError):
        group = None

    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        if group is not None:
            try:
                os.killpg(group, signal_number)
            except (ProcessLookupError, PermissionError):
                pass
        else:
            proc.kill()
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def evaluate_artifact(
    record: TaskRecord,
    artifact: str,
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
) -> Tuple[Optional[bool], Optional[str], float]:
    """Score one artifact against `record`'s task."""

    results, error, elapsed = _run_child(
        items=[{"task_id": record.task_id, "condition": record.condition, "artifact": artifact or ""}],
        config_path=config_path,
        benchmark_config_path=benchmark_config_path,
        wall_timeout_s=wall_timeout_s,
        num_process_evaluate=1,
    )
    if error:
        return None, error, elapsed
    if not results or record.task_id not in results:
        return None, "lcb_eval_returned_none", elapsed
    return bool(results[record.task_id]), None, elapsed


def evaluate_artifacts_batch(
    pairs: Sequence[Tuple[TaskRecord, str]],
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
) -> Tuple[Optional[Dict[str, bool]], Optional[str], float]:
    """Score a chunk of (record, artifact) pairs in one child interpreter.

    Returns `(None, error, elapsed)` if the chunk as a whole timed out or crashed;
    callers should then fall back to per-record evaluation so that one pathological
    program does not discard the rest of the chunk.
    """

    if not pairs:
        return {}, None, 0.0

    task_ids = [record.task_id for record, _ in pairs]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("A chunk must not contain the same task id twice.")

    items = [
        {"task_id": record.task_id, "condition": record.condition, "artifact": artifact or ""}
        for record, artifact in pairs
    ]
    return _run_child(items, config_path, benchmark_config_path, wall_timeout_s)


def evaluate_record(
    record: TaskRecord,
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int,
) -> Tuple[Optional[bool], Optional[str], float]:
    """Score a record's stored final artifact."""

    return evaluate_artifact(
        record=record,
        artifact=record.final_artifact,
        config_path=config_path,
        benchmark_config_path=benchmark_config_path,
        wall_timeout_s=wall_timeout_s,
    )
