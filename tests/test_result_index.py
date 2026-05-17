from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from analysis.result_index import build_run_index, write_run_index, write_tasks_csv
from harness.core.tracker import CostTracker, TaskRecord


class ResultIndexTest(unittest.TestCase):
    def test_build_index_counts_conditions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "run_meta.json").write_text(
                json.dumps(
                    {
                        "benchmark": "livecodebench",
                        "config": "experiments/configs/all_conditions.yaml",
                        "tasks": "experiments/configs/lcb_pilot_10.txt",
                        "conditions": [
                            {
                                "id": "C1",
                                "writer": {
                                    "cli": "claude",
                                    "model": "claude-opus-4-7",
                                    "effort": "medium",
                                },
                                "reviewer": {
                                    "cli": "codex",
                                    "model": "gpt-5.4",
                                    "effort": "medium",
                                },
                            }
                        ],
                    }
                )
            )
            tracker = CostTracker()
            tracker.save(
                TaskRecord(
                    task_id="task-1",
                    condition="C1",
                    benchmark="livecodebench",
                    writer_model="claude-opus-4-7",
                    reviewer_model="gpt-5.4",
                    writer_effort="medium",
                    reviewer_effort="medium",
                    passed=True,
                    total_cost_usd=0.2,
                    final_artifact="print(1)",
                ),
                str(root / "C1"),
            )
            tracker.save(
                TaskRecord(
                    task_id="task-2",
                    condition="C1",
                    benchmark="livecodebench",
                    writer_model="claude-opus-4-7",
                    reviewer_model="gpt-5.4",
                    writer_effort="medium",
                    reviewer_effort="medium",
                    parse_failed=True,
                    cli_error=True,
                ),
                str(root / "C1"),
            )

            index = build_run_index(str(root))
            self.assertEqual("livecodebench", index["benchmark"])
            self.assertEqual(2, index["records"])
            self.assertEqual("medium", index["condition_settings"][0]["writer"]["effort"])
            c1 = index["conditions"][0]
            self.assertEqual("C1", c1["condition"])
            self.assertEqual(1, c1["completed"])
            self.assertEqual(2, c1["attempted"])
            self.assertEqual(1, c1["evaluated"])
            self.assertEqual(1, c1["passed"])
            self.assertEqual(1, c1["parse_failed"])
            self.assertEqual(1, c1["cli_error"])

            index_path = write_run_index(str(root))
            self.assertTrue(index_path.exists())

    def test_tasks_csv_has_one_row_per_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tracker = CostTracker()
            tracker.save(
                TaskRecord(
                    task_id="task-1",
                    condition="B1",
                    benchmark="livecodebench",
                    writer_model="claude-opus-4-7",
                    reviewer_model=None,
                    writer_effort="medium",
                    final_artifact="print(1)",
                ),
                str(root / "B1"),
            )

            csv_path = write_tasks_csv(str(root), str(root / "tasks.csv"))
            with csv_path.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(1, len(rows))
            self.assertEqual("task-1", rows[0]["task_id"])
            self.assertEqual("B1", rows[0]["condition"])
            self.assertEqual("medium", rows[0]["writer_effort"])
            self.assertEqual("print(1)", rows[0]["final_artifact"])


if __name__ == "__main__":
    unittest.main()
