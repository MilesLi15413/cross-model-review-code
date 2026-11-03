from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from analysis.label_study_metrics import compute_paired_tests, compute_summary
from experiments import run_label_study as study
from harness.core.cli_runner import RunResult, UsageLimitError
from harness.core.parser import parse_issues
from harness.core.tracker import CostTracker, TaskRecord

TEMPLATE = Path("harness/prompts/reviewer_lcb_label_study.txt").read_text()
REVIEWERS = [
    {"family": "claude", "cli": "claude", "model": "claude-opus-4-7", "effort": "high"},
    {"family": "gpt", "cli": "codex", "model": "gpt-5.5", "effort": "high"},
    {"family": "gemini", "cli": "gemini", "model": "gemini-3.1-pro-preview", "effort": "high"},
]


def _draft(task_id="t1", family="claude", passed=True, index=0, code="print(1)"):
    cli = {"claude": "claude", "gpt": "codex", "gemini": "gemini"}[family]
    source = TaskRecord(
        task_id=task_id,
        condition="solo",
        benchmark="livecodebench",
        writer_model="model",
        reviewer_model=None,
        writer_cli=cli,
        writer_artifact=code,
        passed=passed,
    )
    return study.Draft(task_id, family, code, passed, source, "source.json", index)


class PromptTest(unittest.TestCase):
    def _prompt(self, label, code="print(1)", evidence=""):
        filled = TEMPLATE.replace("{problem}", "P").replace("{starter_code}", "")
        return study.build_prompt(filled, code, label, evidence)

    def test_arms_differ_only_in_the_label_line(self):
        none_lines = self._prompt("").splitlines()
        true_lines = self._prompt("This code was written by Claude.").splitlines()

        self.assertEqual(len(none_lines) + 1, len(true_lines))
        true_lines.remove("This code was written by Claude.")
        self.assertEqual(none_lines, true_lines)

    def test_true_and_false_differ_only_in_family_name(self):
        true_prompt = self._prompt("This code was written by Claude.")
        false_prompt = self._prompt("This code was written by Gemini.")

        self.assertEqual(true_prompt.replace("Claude.", "Gemini."), false_prompt)

    def test_no_placeholder_survives(self):
        for label in ("", "This code was written by Claude."):
            prompt = self._prompt(label)
            for name in ("{author_label}", "{writer_output}", "{evidence}", "{problem}"):
                self.assertNotIn(name, prompt)

    def test_placeholder_text_in_a_draft_is_not_replaced(self):
        prompt = self._prompt("", code="x = '{author_label} {evidence}'")

        self.assertIn("x = '{author_label} {evidence}'", prompt)

    def test_public_test_evidence_adds_only_the_evidence_block(self):
        plain = self._prompt("")
        block = "\nPUBLIC TEST RESULTS:\n2 of 3 public tests passed.\n"
        with_evidence = self._prompt("", evidence=block)

        self.assertEqual(plain, with_evidence.replace(block, "", 1))


class LabelAssignmentTest(unittest.TestCase):
    def test_false_label_is_never_the_real_family_and_is_deterministic(self):
        for family in study.FAMILY_LABELS:
            for reviewer in study.FAMILY_LABELS:
                for index in range(4):
                    chosen = study.false_family(7, family, reviewer, index)
                    self.assertNotEqual(family, chosen)
                    self.assertEqual(chosen, study.false_family(7, family, reviewer, index))

    def test_false_label_rotates_between_both_wrong_families(self):
        chosen = {study.false_family(7, "claude", "gemini", index) for index in range(2)}

        self.assertEqual({"gemini", "gpt"}, chosen)

    def test_cells_cover_every_draft_reviewer_and_arm(self):
        drafts = [_draft(family=family) for family in study.FAMILY_LABELS]

        cells = study.build_cells(drafts, REVIEWERS, 7)

        self.assertEqual(27, len(cells))
        self.assertEqual(27, len({cell["condition"] for cell in cells}))
        self.assertEqual(9, sum(1 for cell in cells if cell["labeled_family"] is None))
        for cell in cells:
            if cell["arm"] == "true":
                self.assertEqual(cell["draft"].family, cell["labeled_family"])
            if cell["arm"] == "false":
                self.assertNotEqual(cell["draft"].family, cell["labeled_family"])


class ManifestTest(unittest.TestCase):
    def _write(self, directory, name, **fields):
        base = {
            "task_id": "t1",
            "condition": "B1",
            "benchmark": "livecodebench",
            "writer_model": "claude-opus-4-7",
            "reviewer_model": None,
            "writer_cli": "claude",
            "writer_artifact": "print(1)",
            "passed": True,
        }
        base.update(fields)
        path = Path(directory) / name
        path.write_text(json.dumps(base))
        return str(path)

    def test_solo_record_uses_passed_as_draft_outcome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = study.load_draft(self._write(tmpdir, "a.json", passed=False))

        self.assertFalse(draft.passed)
        self.assertEqual("claude", draft.family)

    def test_ungraded_draft_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "a.json", passed=None)
            with self.assertRaises(ValueError):
                study.load_draft(path)

    def test_frozen_checkpoint_is_refused(self):
        with self.assertRaises(SystemExit):
            study.assert_not_frozen("results/raw/lcb_hard_full/labels")
        study.assert_not_frozen("results/raw/demo_labels")


class RunCellTest(unittest.TestCase):
    def _cell(self, arm="none"):
        return {
            "condition": f"L_claude_by_gpt_{arm}",
            "draft": _draft(),
            "reviewer": REVIEWERS[1],
            "arm": arm,
            "labeled_family": None if arm == "none" else "gemini",
        }

    def _result(self, text):
        return RunResult(
            response_text=text,
            raw_stdout="",
            raw_stderr="",
            exit_code=0,
            duration_s=1.0,
            input_tokens=100,
            output_tokens=10,
            cli_version="v1",
        )

    def _run(self, runner, tmpdir, arm="none"):
        return study.run_cell(self._cell(arm), runner, TEMPLATE, CostTracker(), tmpdir, "none", "", 7)

    def test_unchanged_review_is_recorded(self):
        runner = mock.Mock()
        runner.run.return_value = self._result("<issues>none</issues><solution>print(1)</solution>")

        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._run(runner, tmpdir)

        self.assertTrue(record.extra["draft_unchanged"])
        self.assertEqual(0, record.extra["diff_lines"])
        self.assertEqual(0, record.extra["issue_count"])
        self.assertEqual("v1", record.reviewer_cli_version)
        self.assertEqual(0.0, record.writer_cost_usd)

    def test_changed_review_counts_diff_and_issues(self):
        runner = mock.Mock()
        runner.run.return_value = self._result(
            "<issues>\n- wrong bound\n- off by one\n</issues><solution>print(2)</solution>"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._run(runner, tmpdir, arm="false")

        self.assertFalse(record.extra["draft_unchanged"])
        self.assertEqual(2, record.extra["diff_lines"])
        self.assertEqual(2, record.extra["issue_count"])
        self.assertEqual("This code was written by Gemini.", record.extra["label_text"])
        self.assertEqual("other", record.extra["label_relation"])
        self.assertEqual(7, record.extra["label_seed"])

    def test_cli_failure_is_not_recorded_as_an_unchanged_draft(self):
        runner = mock.Mock()
        runner.run.side_effect = RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._run(runner, tmpdir)

        self.assertTrue(record.cli_error)
        self.assertEqual("", record.final_artifact)
        self.assertNotIn("draft_unchanged", record.extra)
        self.assertEqual(study.MAX_ATTEMPTS, record.extra["attempt_count"])

    def test_usage_limit_leaves_no_record(self):
        runner = mock.Mock()
        runner.run.side_effect = UsageLimitError("limit")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(UsageLimitError):
                self._run(runner, tmpdir)
            self.assertEqual([], list(Path(tmpdir).rglob("*.json")))


class IssueParserTest(unittest.TestCase):
    def test_missing_list_is_not_zero_issues(self):
        self.assertIsNone(parse_issues("<solution>x</solution>")["count"])

    def test_bullets_are_counted(self):
        self.assertEqual(2, parse_issues("<issues>\n- a\n- b\n</issues>")["count"])

    def test_tags_inside_code_are_ignored(self):
        text = "<issues>none</issues><solution><issues>\n- a\n</issues></solution>"

        self.assertEqual(0, parse_issues(text)["count"])


def _result_record(task, reviewer, writer, arm, relation, unchanged, writer_passed, passed, issues=1):
    return {
        "task_id": task,
        "writer_passed": writer_passed,
        "passed": passed,
        "cli_error": False,
        "timed_out": False,
        "parse_failed": False,
        "extra": {
            "reviewer_family": reviewer,
            "writer_family": writer,
            "label_arm": arm,
            "label_relation": relation,
            "draft_unchanged": unchanged,
            "diff_lines": 0 if unchanged else 4,
            "issue_count": issues,
        },
    }


class MetricsTest(unittest.TestCase):
    def _records(self):
        return [
            _result_record("t1", "gpt", "claude", "none", "none", True, False, False, 0),
            _result_record("t2", "gpt", "claude", "none", "none", False, True, True, 2),
            _result_record("t1", "gpt", "claude", "true", "other", False, False, True, 3),
            _result_record("t2", "gpt", "claude", "true", "other", False, True, False, 3),
        ]

    def test_summary_compares_each_arm_with_none(self):
        rows = compute_summary(self._records(), "label_arm")
        true_row = next(row for row in rows if row["label_arm"] == "true")

        self.assertEqual(0.0, true_row["unchanged_rate"])
        self.assertEqual(-0.5, true_row["unchanged_rate_vs_none"])
        self.assertEqual(1.0, true_row["fix_rate"])
        self.assertEqual(1.0, true_row["fix_rate_vs_none"])
        self.assertEqual(1.0, true_row["regression_rate"])
        self.assertEqual(2.0, true_row["mean_issue_count_vs_none"])

    def test_paired_tests_use_the_same_drafts(self):
        rows = compute_paired_tests(self._records())
        by_metric = {row["metric"]: row for row in rows}

        self.assertEqual(2, by_metric["unchanged"]["n_pairs"])
        self.assertEqual(1, by_metric["unchanged"]["none_only"])
        self.assertEqual(1, by_metric["fix"]["n_pairs"])
        self.assertEqual(1, by_metric["regression"]["n_pairs"])

    def test_invalid_records_are_counted_not_scored(self):
        records = self._records()
        records[2]["cli_error"] = True
        true_row = next(
            row for row in compute_summary(records, "label_arm") if row["label_arm"] == "true"
        )

        self.assertEqual(1, true_row["n_invalid"])
        self.assertEqual(1, true_row["n_valid"])


if __name__ == "__main__":
    unittest.main()
