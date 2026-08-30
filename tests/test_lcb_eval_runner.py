from __future__ import annotations

import unittest
from unittest import mock

from analysis import lcb_eval_runner
from harness.core.tracker import TaskRecord


def _record(task_id: str) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        condition="C2",
        benchmark="livecodebench",
        writer_model="gpt-5.5",
        reviewer_model="claude-opus-4-7",
        writer_artifact="print(1)",
        final_artifact="print(2)",
    )


class EvalRunnerTest(unittest.TestCase):
    def test_child_script_exists(self):
        self.assertTrue(lcb_eval_runner.CHILD_SCRIPT.exists())

    def test_duplicate_task_ids_in_a_chunk_are_rejected(self):
        """evaluate_batch keys results by task id, so a repeat would silently vanish."""

        with self.assertRaises(ValueError):
            lcb_eval_runner.evaluate_artifacts_batch(
                [(_record("t1"), "print(1)"), (_record("t1"), "print(2)")],
                "config.yaml",
                "benchmark.yaml",
                60,
            )

    def test_empty_chunk_short_circuits(self):
        results, error, elapsed = lcb_eval_runner.evaluate_artifacts_batch(
            [], "config.yaml", "benchmark.yaml", 60
        )

        self.assertEqual({}, results)
        self.assertIsNone(error)
        self.assertEqual(0.0, elapsed)

    def test_evaluate_artifact_scores_the_given_artifact_not_the_stored_final(self):
        record = _record("t1")
        with mock.patch.object(
            lcb_eval_runner, "_run_child", return_value=({"t1": True}, None, 1.0)
        ) as run_child:
            passed, error, _ = lcb_eval_runner.evaluate_artifact(
                record, record.writer_artifact, "config.yaml", "benchmark.yaml", 60
            )

        self.assertTrue(passed)
        self.assertIsNone(error)
        sent = run_child.call_args.kwargs["items"]
        self.assertEqual([{"task_id": "t1", "condition": "C2", "artifact": "print(1)"}], sent)

    def test_missing_result_for_a_task_is_an_error_not_a_failure(self):
        """A task the evaluator never scored must not be recorded as a failed program."""

        record = _record("t1")
        with mock.patch.object(lcb_eval_runner, "_run_child", return_value=({}, None, 1.0)):
            passed, error, _ = lcb_eval_runner.evaluate_artifact(
                record, record.writer_artifact, "config.yaml", "benchmark.yaml", 60
            )

        self.assertIsNone(passed)
        self.assertEqual("lcb_eval_returned_none", error)


if __name__ == "__main__":
    unittest.main()
