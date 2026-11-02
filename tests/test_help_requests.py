from __future__ import annotations

import unittest
from pathlib import Path

from analysis.help_requests import summarize_model
from harness.core.parser import parse_help_requests, parse_model_response
from harness.core.tracker import CostTracker, TaskRecord


def _tracking(text):
    return parse_help_requests(text, parse_model_response(text))


class HelpParserTest(unittest.TestCase):
    def test_tagged_requests_are_counted_with_types(self):
        text = (
            '<help_request type="wants_execution">Run the samples.</help_request>\n'
            '<help_request type="made_up">Hmm.</help_request>\n'
            "<solution>print(1)</solution>"
        )

        tracking = _tracking(text)

        self.assertEqual(2, tracking["tagged_count"])
        self.assertEqual(
            ["wants_execution", "other"],
            [request["type"] for request in tracking["tagged_requests"]],
        )
        self.assertEqual("made_up", tracking["tagged_requests"][1]["raw_type"])
        self.assertFalse(tracking["no_code"])

    def test_clarification_and_uncertainty_types_are_kept(self):
        text = (
            '<help_request type="clarification">Is i < j?</help_request>\n'
            '<help_request type="uncertainty">Might be too slow.</help_request>\n'
            "<solution>print(1)</solution>"
        )

        self.assertEqual(
            ["clarification", "uncertainty"],
            [request["type"] for request in _tracking(text)["tagged_requests"]],
        )

    def test_untagged_requests_are_counted_separately(self):
        text = "Could you clarify the limits? I can't run this.\n<solution>print(1)</solution>"

        tracking = _tracking(text)

        self.assertEqual(0, tracking["tagged_count"])
        self.assertEqual(2, tracking["untagged_count"])

    def test_tagged_text_and_code_are_not_counted_as_untagged(self):
        text = (
            '<help_request type="other">Could you clarify this?</help_request>\n'
            "<solution># please provide input\nprint(1)</solution>"
        )

        self.assertEqual(0, _tracking(text)["untagged_count"])

    def test_reply_without_code_is_flagged(self):
        self.assertTrue(_tracking("I need more information before I can start.")["no_code"])

    def test_code_block_without_tags_is_code(self):
        self.assertFalse(_tracking("```python\nprint(1)\n```")["no_code"])

    def test_unclosed_tag_is_malformed(self):
        self.assertEqual(1, _tracking('<help_request type="other">oops')["malformed_tags"])

    def test_help_template_only_adds_the_instruction_block(self):
        base = Path("harness/prompts/writer_lcb.txt").read_text()
        help_prompt = Path("harness/prompts/writer_lcb_help.txt").read_text()
        head, tail = base.split("Output your solution inside")

        self.assertTrue(help_prompt.startswith(head))
        self.assertTrue(help_prompt.endswith("Output your solution inside" + tail))
        self.assertIn("<help_request", help_prompt)
        self.assertIn("CONTINUE", help_prompt)

    def test_v2_template_only_changes_the_help_block(self):
        v1 = Path("harness/prompts/writer_lcb_help.txt").read_text()
        v2 = Path("harness/prompts/writer_lcb_help_v2.txt").read_text()

        self.assertEqual(v1.split("If at any point")[0], v2.split("Whenever you are unsure")[0])
        self.assertEqual(v1.split("Output your solution inside")[1], v2.split("Output your solution inside")[1])
        for request_type in ("missing_information", "clarification", "uncertainty"):
            self.assertIn(request_type, v2)


class HelpTrackingTest(unittest.TestCase):
    def test_no_code_reply_counts_as_complete_for_help_conditions(self):
        record = TaskRecord(
            task_id="t",
            condition="H1",
            benchmark="livecodebench",
            writer_model="m",
            reviewer_model=None,
            parse_failed=True,
            final_artifact="I need more information.",
            extra={"help_tracking": {}},
        )

        self.assertTrue(CostTracker().record_is_complete(record))

    def test_summary_reports_requests_and_pass_rates(self):
        def record(task_id, passed, text):
            return {
                "task_id": task_id,
                "writer_model": "m",
                "passed": passed,
                "extra": {"help_tracking": _tracking(text)},
            }

        records = [
            record("t1", True, '<help_request type="wants_execution">x</help_request><solution>a</solution>'),
            record("t2", False, "<solution>a</solution>"),
            record("t3", True, "<solution>a</solution>"),
            {"task_id": "t4", "writer_model": "m", "passed": None, "extra": {}},
        ]

        row = summarize_model("m", records)

        self.assertEqual(4, row["tasks"])
        self.assertEqual(1, row["invalid_calls"])
        self.assertEqual(1, row["tagged_requests"])
        self.assertEqual(1, row["type_wants_execution"])
        self.assertEqual(1.0, row["pass_rate_with_requests"])
        self.assertEqual(0.5, row["pass_rate_without_requests"])

    def test_summary_compares_uncertainty_and_confidence_with_passing(self):
        def record(passed, text, confidence):
            return {
                "task_id": "t",
                "writer_model": "m",
                "passed": passed,
                "writer_confidence_label": confidence,
                "extra": {"help_tracking": _tracking(text)},
            }

        records = [
            record(False, '<help_request type="uncertainty">x</help_request><solution>a</solution>', "low"),
            record(True, '<help_request type="uncertainty">x</help_request><solution>a</solution>', "high"),
            record(True, "<solution>a</solution>", "high"),
            record(True, "<solution>a</solution>", None),
        ]

        row = summarize_model("m", records)

        self.assertEqual(2, row["type_uncertainty"])
        self.assertEqual(0.5, row["pass_rate_with_uncertainty"])
        self.assertEqual(1.0, row["pass_rate_without_uncertainty"])
        self.assertEqual(2, row["n_confidence_high"])
        self.assertEqual(1.0, row["pass_rate_confidence_high"])
        self.assertEqual(0.0, row["pass_rate_confidence_low"])
        self.assertEqual(1, row["n_confidence_missing"])


if __name__ == "__main__":
    unittest.main()
