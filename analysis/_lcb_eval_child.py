"""Child entry point: score artifacts in a fresh interpreter and emit JSON.

Isolation here is deliberately a *new* interpreter rather than a forked child.
LiveCodeBench's evaluator runs candidate programs through its own multiprocessing
pool, and nesting that inside a forked process makes it return failures for every
sample instead of raising, which silently turns a whole evaluation run into zeros.
A fresh process gives the same crash and hang isolation without that trap.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiment import get_adapter, merge_configs
from harness.core.parser import normalize_code_artifact
from harness.core.tracker import TaskRecord


def main() -> None:
    payload_path, output_path = sys.argv[1], sys.argv[2]
    payload = json.loads(Path(payload_path).read_text())

    config = merge_configs(payload["config"], "livecodebench", payload["benchmark_config"])
    if payload.get("num_process_evaluate"):
        config["benchmark_config"]["num_process_evaluate"] = int(payload["num_process_evaluate"])
    adapter = get_adapter("livecodebench", config)

    records = [
        TaskRecord(
            task_id=str(item["task_id"]),
            condition=str(item.get("condition", "")),
            benchmark="livecodebench",
            writer_model="",
            reviewer_model=None,
            final_artifact=normalize_code_artifact(item.get("artifact") or ""),
        )
        for item in payload["items"]
    ]
    adapter.load_tasks(sorted({record.task_id for record in records}))
    results = adapter.evaluate_batch(records)
    Path(output_path).write_text(json.dumps(results))


if __name__ == "__main__":
    main()
