from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

from harness.benchmarks.livecodebench import adapter as lcb_adapter_module
from harness.benchmarks.swebench import adapter as swe_adapter_module
from harness.benchmarks.swebench import batch_eval as swe_batch_eval_module
from harness.benchmarks.swebench.batch_eval import _build_predictions
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

    def test_swebench_prediction_shape(self):
        predictions = _build_predictions(
            [
                {
                    "task_id": "repo__issue-1",
                    "condition": "C2",
                    "final_artifact": "diff --git a/foo b/foo",
                    "reviewer_stdout": "final patch",
                    "writer_stdout": "draft patch",
                    "cli_error": False,
                    "timed_out": False,
                }
            ],
            "C2",
        )
        self.assertEqual(1, len(predictions))
        prediction = predictions[0]
        self.assertEqual("repo__issue-1", prediction["instance_id"])
        self.assertEqual("C2", prediction["model_name_or_path"])
        self.assertEqual("diff --git a/foo b/foo", prediction["model_patch"])
        self.assertEqual("final patch", prediction["full_output"])

    def test_swebench_batch_eval_uses_absolute_predictions_path(self):
        record = {
            "task_id": "repo__issue-1",
            "condition": "B1",
            "final_artifact": "diff --git a/foo b/foo",
            "writer_stdout": "patch",
            "cli_error": False,
            "timed_out": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs_dir = root / "inputs" / "B1"
            inputs_dir.mkdir(parents=True)
            (inputs_dir / "repo__issue-1__B1.json").write_text(json.dumps(record))

            output_dir = root / "eval"
            report_name = "B1.B1-20260425T000000Z.json"
            report_path = root / report_name
            report_path.write_text(
                json.dumps(
                    {
                        "submitted_ids": ["repo__issue-1"],
                        "resolved_ids": [],
                        "unresolved_ids": ["repo__issue-1"],
                        "error_ids": [],
                    }
                )
            )

            completed = mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch.object(swe_batch_eval_module, "SWE_ROOT", root):
                with mock.patch.object(swe_batch_eval_module, "_now_slug", return_value="20260425T000000Z"):
                    with mock.patch("harness.benchmarks.swebench.batch_eval.subprocess.run", return_value=completed) as run_mock:
                        swe_batch_eval_module.run_batch_eval(
                            inputs_dir=str(root / "inputs"),
                            output_dir=str(output_dir),
                            dataset_name="princeton-nlp/SWE-bench_Verified",
                            split="test",
                            max_workers=1,
                            timeout=60,
                        )

            cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args.args[0]
            predictions_idx = cmd.index("--predictions_path") + 1
            self.assertTrue(Path(cmd[predictions_idx]).is_absolute())
            self.assertTrue((output_dir / "B1" / "predictions.jsonl").exists())

    def test_swebench_adapter_falls_back_to_hf_when_local_dataset_missing(self):
        fake_rows = [
            {
                "instance_id": "repo__issue-1",
                "repo": "repo",
                "problem_statement": "Issue text",
                "base_commit": "abc123",
                "hints_text": "Hint",
            }
        ]
        with tempfile.TemporaryDirectory() as fake_root:
            with mock.patch.object(swe_adapter_module, "SWE_ROOT", Path(fake_root)):
                with mock.patch.object(
                    swe_adapter_module,
                    "load_dataset",
                    return_value=fake_rows,
                ) as load_mock:
                    adapter = swe_adapter_module.SWEBenchAdapter(
                        dataset_path="missing.json",
                        dataset_name="princeton-nlp/SWE-bench_Verified",
                        split="test",
                    )
                    tasks = adapter.load_tasks(["repo__issue-1"])

        self.assertEqual(["repo__issue-1"], [task.task_id for task in tasks])
        load_mock.assert_called_once_with("princeton-nlp/SWE-bench_Verified", split="test")

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
