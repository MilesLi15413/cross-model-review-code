"""Build the public-test evidence text shown to reviewers in the label study."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
CHILD_SCRIPT = Path(__file__).resolve().parent / "_public_tests_child.py"


def run_public_tests(
    task_id: str,
    draft: str,
    config_path: str,
    benchmark_config_path: str,
    wall_timeout_s: int = 300,
) -> Dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="lcb_public_") as tmp_dir:
        tmp = Path(tmp_dir)
        payload_path = tmp / "payload.json"
        output_path = tmp / "result.json"
        payload_path.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "draft": draft,
                    "config": config_path,
                    "benchmark_config": benchmark_config_path,
                }
            )
        )
        subprocess.run(
            [sys.executable, str(CHILD_SCRIPT), str(payload_path), str(output_path)],
            cwd=str(ROOT),
            check=True,
            timeout=wall_timeout_s,
        )
        return json.loads(output_path.read_text())


def format_feedback(result: Dict[str, int]) -> str:
    return f"\nPUBLIC TEST RESULTS:\n{result['passed']} of {result['total']} public tests passed.\n"
