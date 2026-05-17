from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from harness.core.cli_runner import RunResult
from harness.core.pipeline import BenchmarkTask, TwoPassPipeline
from harness.core.tracker import CostTracker


class FakeRunner:
    def __init__(self, responses):
        self.cli = "fake"
        self.model = "fake-model"
        self.effort = "medium"
        self.timeout_s = 300
        self.paused_sentinel_path = None
        self.status_callback = None
        self.responses = list(responses)
        self.calls = 0

    def get_version(self):
        return "fake 1.0"

    def run(self, prompt, task_id=None, condition_id=None, turn=None):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return RunResult(
            response_text=response,
            raw_stdout=response,
            raw_stderr="",
            exit_code=0,
            duration_s=1.0,
            cli_version="fake 1.0",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
        )


class PipelineRetryTest(unittest.TestCase):
    def _task(self):
        return BenchmarkTask(
            task_id="task-1",
            benchmark="livecodebench",
            writer_prompt="write solution",
            reviewer_prompt_template="review {writer_output}",
            metadata={},
        )

    def test_retries_until_writer_returns_parseable_solution(self):
        writer = FakeRunner(["", "```python\nprint(1)\n```", "<solution>print(2)</solution>"])
        pipeline = TwoPassPipeline(
            writer=writer,
            reviewer=None,
            tracker=CostTracker(),
            condition_id="C1",
            max_task_attempts=3,
        )

        result = pipeline.run_task(self._task())

        self.assertEqual(3, writer.calls)
        self.assertEqual("print(2)", result.final_artifact)
        self.assertFalse(result.record.parse_failed)
        self.assertEqual(3, result.record.extra["attempt_count"])
        self.assertEqual(
            ["parse_failed", "parse_failed"],
            result.record.extra["retry_reasons"],
        )

    def test_returns_final_incomplete_record_after_three_retries(self):
        writer = FakeRunner(["", "", "", ""])
        pipeline = TwoPassPipeline(
            writer=writer,
            reviewer=None,
            tracker=CostTracker(),
            condition_id="C1",
            max_task_attempts=4,
        )

        result = pipeline.run_task(self._task())

        self.assertEqual(4, writer.calls)
        self.assertEqual("", result.final_artifact)
        self.assertTrue(result.record.parse_failed)
        self.assertEqual(4, result.record.extra["attempt_count"])
        self.assertEqual(
            ["parse_failed", "parse_failed", "parse_failed", "parse_failed"],
            result.record.extra["retry_reasons"],
        )
        self.assertEqual("parse_failed", result.record.extra["incomplete_reason"])

    def test_prints_full_cli_error_for_incomplete_result(self):
        writer = FakeRunner(
            [
                RuntimeError("first failure line\nsecond failure line"),
                RuntimeError("final failure line\nfinal detail line"),
            ]
        )
        pipeline = TwoPassPipeline(
            writer=writer,
            reviewer=None,
            tracker=CostTracker(),
            condition_id="C1",
            max_task_attempts=2,
        )

        output = io.StringIO()
        with redirect_stdout(output):
            result = pipeline.run_task(self._task())

        text = output.getvalue()
        self.assertTrue(result.record.cli_error)
        self.assertIn("returned incomplete result (cli_error); retrying 2/2", text)
        self.assertIn("returned incomplete result (cli_error); exhausted 2/2 attempts", text)
        self.assertIn("writer_error:\nfirst failure line\nsecond failure line", text)
        self.assertIn("writer_error:\nfinal failure line\nfinal detail line", text)


if __name__ == "__main__":
    unittest.main()
