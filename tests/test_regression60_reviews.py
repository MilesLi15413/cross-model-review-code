from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments import run_regression60_reviews as rr
from harness.core.cli_runner import OutOfCreditsError, RunResult
from harness.core.tracker import CostTracker, TaskRecord

DRAFT = "class Solution:\n    def f(self):\n        return 1\n"


def make_cell(reviewer="gemini"):
    src = TaskRecord(task_id="t1", condition="B1_claude_solo", benchmark="livecodebench",
                     writer_model="claude-opus-4-7", reviewer_model=None, writer_cli="claude",
                     writer_input_tokens=1000, writer_output_tokens=5000, writer_cost_usd=0.5,
                     writer_artifact=DRAFT, passed=True)
    return rr.Cell(rr.Draft("t1", "claude", "src.json", src), reviewer)


def result(text, cost=None):
    return RunResult(response_text=text, raw_stdout="{}", raw_stderr="", exit_code=0, duration_s=2.0,
                     input_tokens=100, output_tokens=200, cost_usd=cost, cli_version="v1")


class RegressionReviewsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ckpt = str(Path(self.tmp.name) / "regression60_reviews")
        self.tracker = CostTracker("experiments/configs/pricing.yaml")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchanged_review_and_cost_is_review_only(self):
        runner = mock.Mock()
        runner.run.return_value = result(f"<solution>\n{DRAFT}</solution>")
        rec = rr.run_cell(make_cell(), runner, "P {writer_output}", self.tracker, self.ckpt)
        self.assertTrue(rec.extra["unchanged_exact"])
        self.assertEqual(0, rec.extra["diff_lines"])
        self.assertEqual(0.0, rec.writer_cost_usd)
        expected = self.tracker.compute_cost("gemini-3.1-pro-preview", 100, 200)
        self.assertAlmostEqual(expected, rec.total_cost_usd)
        self.assertEqual("none", rec.extra["author_label"])
        self.assertEqual("done", rr.cell_status(self.tracker, self.ckpt, make_cell()))
        prompt = runner.run.call_args[0][0]
        self.assertEqual(f"P {DRAFT}", prompt)

    def test_edit_counts_changed_lines(self):
        runner = mock.Mock()
        runner.run.return_value = result("<solution>\nclass Solution:\n    def f(self):\n        return 2\n</solution>")
        rec = rr.run_cell(make_cell(), runner, "{writer_output}", self.tracker, self.ckpt)
        self.assertFalse(rec.extra["unchanged_exact"])
        self.assertEqual(2, rec.extra["diff_lines"])

    def test_whitespace_only_change(self):
        runner = mock.Mock()
        runner.run.return_value = result("<solution>\nclass Solution:   \n\n    def f(self):\n        return 1\n</solution>")
        rec = rr.run_cell(make_cell(), runner, "{writer_output}", self.tracker, self.ckpt)
        self.assertFalse(rec.extra["unchanged_exact"])
        self.assertTrue(rec.extra["unchanged_whitespace"])

    def test_out_of_credits_saves_nothing(self):
        runner = mock.Mock()
        runner.run.side_effect = OutOfCreditsError("402")
        with self.assertRaises(OutOfCreditsError):
            rr.run_cell(make_cell(), runner, "{writer_output}", self.tracker, self.ckpt)
        self.assertEqual(1, runner.run.call_count)
        self.assertEqual("todo", rr.cell_status(self.tracker, self.ckpt, make_cell()))

    def test_errors_are_capped_across_runs(self):
        runner = mock.Mock()
        runner.run.side_effect = RuntimeError("boom")
        rr.run_cell(make_cell(), runner, "{writer_output}", self.tracker, self.ckpt)
        self.assertEqual(rr.MAX_ATTEMPTS, runner.run.call_count)
        self.assertEqual("failed_final", rr.cell_status(self.tracker, self.ckpt, make_cell()))

    def test_parse_failure_then_success_counts_both_costs(self):
        runner = mock.Mock()
        runner.run.side_effect = [result(""), result(f"<solution>\n{DRAFT}</solution>")]
        rec = rr.run_cell(make_cell(), runner, "{writer_output}", self.tracker, self.ckpt)
        one = self.tracker.compute_cost("gemini-3.1-pro-preview", 100, 200)
        self.assertAlmostEqual(2 * one, rec.extra["reviewer_cost_all_attempts"])
        self.assertAlmostEqual(2 * one, rr.family_spend(self.tracker, self.ckpt)["gemini"])

    def test_refuses_frozen_and_unprefixed_dirs(self):
        with self.assertRaises(SystemExit):
            rr.assert_not_frozen("results/raw/lcb_hard_full/x")
        with self.assertRaises(SystemExit):
            rr.assert_not_frozen(str(Path(self.tmp.name) / "other"))

    def test_failing_draft_records_writer_failed(self):
        cell = make_cell()
        cell.draft.passed = False
        runner = mock.Mock()
        runner.run.return_value = result(f"<solution>\n{DRAFT}</solution>")
        rec = rr.run_cell(cell, runner, "{writer_output}", self.tracker, self.ckpt)
        self.assertIs(False, rec.writer_passed)

    def test_gpt_reviewer_uses_isolated_codex_home(self):
        self.assertTrue(rr.REVIEWERS["gpt55"]["codex_home"].endswith(".codex-regression60"))


if __name__ == "__main__":
    unittest.main()
