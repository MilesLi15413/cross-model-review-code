from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

from harness.benchmarks.livecodebench import adapter as lcb_adapter_module
from harness.core.tracker import TaskRecord


class AdapterHelpersTest(unittest.TestCase):
    def test_livecodebench_custom_output_shape(self):
        with tempfile.TemporaryDirectory() as dataset_dir:
            dataset_path = Path(dataset_dir)
            (dataset_path / "task_a.json").write_text(
                json.dumps({"task_id": "task_a", "question_content": "Q1"})
            )
            (dataset_path / "task_b.json").write_text(
                json.dumps({"task_id": "task_b", "question_content": "Q2"})
            )

            with tempfile.TemporaryDirectory() as fake_root:
                with mock.patch.object(lcb_adapter_module, "LCB_ROOT", Path(fake_root)):
                    adapter = lcb_adapter_module.LiveCodeBenchAdapter(dataset_path=str(dataset_path))
                    record = TaskRecord(
                        task_id="task_a",
                        condition="C1",
                        benchmark="livecodebench",
                        writer_model="claude-opus-4-7",
                        reviewer_model="gpt-5.4",
                        final_artifact="print(1)",
                    )
                    outputs = adapter._build_custom_outputs([record])

            self.assertEqual(2, len(outputs))
            by_id = {row["question_id"]: row for row in outputs}
            self.assertEqual(["print(1)"], by_id["task_a"]["code_list"])
            self.assertEqual([""], by_id["task_b"]["code_list"])

    def test_livecodebench_load_tasks_batches_hf_fetch(self):
        rows = [
            (
                1,
                2,
                "test1.jsonl",
                {
                    "question_id": "task_a",
                    "question_title": "A",
                    "question_content": "Question A",
                    "difficulty": "easy",
                    "starter_code": "",
                    "platform": "atcoder",
                    "contest_id": "abc",
                    "contest_date": "2026-01-01T00:00:00",
                    "public_test_cases": "[]",
                    "private_test_cases": "[]",
                    "metadata": "{}",
                },
            ),
            (
                1,
                2,
                "test1.jsonl",
                {
                    "question_id": "task_b",
                    "question_title": "B",
                    "question_content": "Question B",
                    "difficulty": "medium",
                    "starter_code": "",
                    "platform": "atcoder",
                    "contest_id": "abc",
                    "contest_date": "2026-01-01T00:00:00",
                    "public_test_cases": "[]",
                    "private_test_cases": "[]",
                    "metadata": "{}",
                },
            ),
        ]

        with tempfile.TemporaryDirectory() as fake_root:
            with mock.patch.object(lcb_adapter_module, "LCB_ROOT", Path(fake_root)):
                with mock.patch.object(
                    lcb_adapter_module,
                    "iter_hf_lcb_rows_with_files",
                    return_value=iter(rows),
                ) as fetch_mock:
                    adapter = lcb_adapter_module.LiveCodeBenchAdapter(dataset_path="missing-dir")
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        tasks = adapter.load_tasks(["task_a", "task_b"])

        self.assertEqual(["task_a", "task_b"], [task.task_id for task in tasks])
        self.assertEqual(1, fetch_mock.call_count)
        output = stdout.getvalue()
        self.assertIn("Fetching 2 LiveCodeBench task rows from Hugging Face", output)
        self.assertIn("Scanning LiveCodeBench shard test1.jsonl", output)


if __name__ == "__main__":
    unittest.main()
