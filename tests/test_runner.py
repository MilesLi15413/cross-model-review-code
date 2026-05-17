from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.run_experiment import (
    _confirm_resume,
    build_pipeline,
    ensure_task_file,
    infer_task_count,
    infer_lcb_difficulty,
    merge_configs,
    resolve_tasks_path,
    save_run_meta,
)
from harness.core.tracker import CostTracker, TaskRecord


class RunnerHelpersTest(unittest.TestCase):
    def test_merge_configs_uses_benchmark_specific_yaml(self):
        config = merge_configs(
            "experiments/configs/all_conditions.yaml",
            "livecodebench",
        )
        self.assertIn("conditions", config)
        self.assertEqual("external/livecodebench/data", config["benchmark_config"]["dataset_path"])
        self.assertEqual("high", config["conditions"][0]["writer"]["effort"])

    def test_checkpoint_save_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                final_artifact="print(1)",
            )
            tracker.save(record, tmpdir)
            tracker.save(record, tmpdir)
            files = list(Path(tmpdir).glob("*.json"))
            self.assertEqual(1, len(files))
            self.assertTrue(tracker.is_done("task-1", "C1", tmpdir))

    def test_resume_reruns_cli_error_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                cli_error=True,
            )
            tracker.save(record, tmpdir)
            self.assertFalse(tracker.is_done("task-1", "C1", tmpdir))

    def test_resume_reruns_timed_out_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                timed_out=True,
            )
            tracker.save(record, tmpdir)
            self.assertFalse(tracker.is_done("task-1", "C1", tmpdir))

    def test_resume_keeps_successful_unevaluated_batch_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                cli_error=False,
                timed_out=False,
                passed=None,
                final_artifact="print(1)",
            )
            tracker.save(record, tmpdir)
            self.assertTrue(tracker.is_done("task-1", "C1", tmpdir))

    def test_resume_reruns_empty_artifact_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                cli_error=False,
                timed_out=False,
                parse_failed=False,
                final_artifact="",
            )
            tracker.save(record, tmpdir)
            self.assertFalse(tracker.is_done("task-1", "C1", tmpdir))

    def test_resume_reruns_parse_failed_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="task-1",
                condition="C1",
                benchmark="livecodebench",
                writer_model="claude-opus-4-7",
                reviewer_model="gpt-5.4",
                cli_error=False,
                timed_out=False,
                parse_failed=True,
                final_artifact="print(1)",
            )
            tracker.save(record, tmpdir)
            self.assertFalse(tracker.is_done("task-1", "C1", tmpdir))

    def test_confirm_resume_flag_clears_pause_sentinel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentinel = Path(tmpdir) / "PAUSED"
            payload = {
                "blocked_condition": "C1",
                "last_task_id": "task-1",
                "cli": "claude",
                "model": "claude-opus-4-7",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            sentinel.write_text(json.dumps(payload))
            _confirm_resume(tmpdir, payload, confirm_resume=True)
            self.assertFalse(sentinel.exists())

    def test_infer_task_count_from_filename(self):
        self.assertEqual(100, infer_task_count("experiments/configs/lcb_100.txt", "livecodebench"))
        self.assertEqual(10, infer_task_count("experiments/configs/lcb_pilot_10.txt", "livecodebench"))

    def test_resolve_tasks_path_uses_benchmark_default(self):
        self.assertEqual(
            "experiments/configs/lcb_100.txt",
            resolve_tasks_path("livecodebench", None),
        )

    def test_resolve_tasks_path_uses_hard_only_default_for_livecodebench(self):
        self.assertEqual(
            "experiments/configs/lcb_hard_100.txt",
            resolve_tasks_path("livecodebench", None, "hard"),
        )

    def test_infer_lcb_difficulty_from_filename(self):
        self.assertEqual("hard", infer_lcb_difficulty("experiments/configs/lcb_hard_100.txt"))
        self.assertEqual("medium", infer_lcb_difficulty("experiments/configs/lcb_medium_50.txt"))
        self.assertIsNone(infer_lcb_difficulty("experiments/configs/lcb_100.txt"))

    def test_ensure_task_file_samples_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "lcb_7.txt"
            config = {"dataset_path": "external/livecodebench/data", "release_version": "release_latest"}
            with unittest.mock.patch(
                "harness.benchmarks.livecodebench.task_sampler.sample_tasks",
                return_value=["a", "b"],
            ) as sample_mock:
                resolved = ensure_task_file("livecodebench", config, str(output_path))

            self.assertEqual(str(output_path), resolved)
            sample_mock.assert_called_once_with(
                "external/livecodebench/data",
                str(output_path),
                total=7,
                release_version="release_latest",
                difficulty=None,
            )

    def test_ensure_task_file_samples_hard_only_livecodebench(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "lcb_hard_9.txt"
            config = {"dataset_path": "external/livecodebench/data", "release_version": "release_latest"}
            with unittest.mock.patch(
                "harness.benchmarks.livecodebench.task_sampler.sample_tasks",
                return_value=["a", "b"],
            ) as sample_mock:
                resolved = ensure_task_file("livecodebench", config, str(output_path))

            self.assertEqual(str(output_path), resolved)
            sample_mock.assert_called_once_with(
                "external/livecodebench/data",
                str(output_path),
                total=9,
                release_version="release_latest",
                difficulty="hard",
            )

    def test_build_pipeline_passes_effort_to_writer_and_reviewer(self):
        tracker = CostTracker()
        condition = {
            "id": "C1",
            "writer": {
                "cli": "claude",
                "model": "claude-opus-4-7",
                "effort": "medium",
                "timeout_s": 300,
            },
            "reviewer": {
                "cli": "codex",
                "model": "gpt-5.4",
                "effort": "medium",
                "timeout_s": 300,
            },
        }

        pipeline = build_pipeline(condition, tracker, "/tmp/checkpoint")

        self.assertEqual("medium", pipeline.writer.effort)
        self.assertEqual("medium", pipeline.reviewer.effort)

    def test_save_run_meta_includes_effort_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_run_meta(
                checkpoint_dir=tmpdir,
                benchmark="livecodebench",
                config_path="experiments/configs/all_conditions.yaml",
                benchmark_config_path="experiments/configs/livecodebench.yaml",
                tasks_path="experiments/configs/lcb_pilot_10.txt",
                skip_eval=False,
                skip_preflight=False,
                conditions=[
                    {
                        "id": "B1",
                        "writer": {
                            "cli": "claude",
                            "model": "claude-opus-4-7",
                            "effort": "medium",
                        },
                        "reviewer": None,
                    }
                ],
            )

            payload = json.loads((Path(tmpdir) / "run_meta.json").read_text())

        self.assertEqual("medium", payload["conditions"][0]["writer"]["effort"])


if __name__ == "__main__":
    unittest.main()
