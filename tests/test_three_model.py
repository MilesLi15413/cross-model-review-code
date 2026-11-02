from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import yaml

from analysis.compute_metrics import compute_metrics
from analysis.plots import CONDITION_LABELS, COLORS
from analysis.review_transitions import compute_transitions
from analysis.statistical_tests import benjamini_hochberg
from experiments.run_experiment import select_conditions, task_for_condition
from harness.core.pipeline import BenchmarkTask
from harness.core.preflight import build_preflight_runners

ORIGINAL = yaml.safe_load(Path("experiments/configs/all_conditions.yaml").read_text())["conditions"]
THREE = yaml.safe_load(Path("experiments/configs/three_model_conditions.yaml").read_text())["conditions"]


class ThreeModelConfigTest(unittest.TestCase):
    def test_original_conditions_are_unchanged(self):
        by_id = {condition["id"]: condition for condition in THREE}

        for condition in ORIGINAL:
            self.assertEqual(condition, by_id[condition["id"]])

    def test_twelve_conditions_cover_every_pair(self):
        def key(turn):
            return turn["model"] if turn else None

        pairs = {(key(c["writer"]), key(c["reviewer"])) for c in THREE}

        self.assertEqual(12, len(THREE))
        self.assertEqual(12, len(pairs))
        self.assertEqual(3, sum(1 for c in THREE if c["reviewer"] is None))
        self.assertEqual({100.0}, {c["per_task_budget_usd"] for c in THREE})
        self.assertEqual({30000}, {c["writer"]["timeout_s"] for c in THREE})

    def test_every_condition_has_a_plot_label_and_color(self):
        for condition in THREE:
            short = condition["id"].split("_", 1)[0]
            self.assertNotIn("5.4", CONDITION_LABELS[short])
            self.assertIn(short, COLORS)

    def test_preflight_covers_three_models(self):
        runners = build_preflight_runners(THREE)

        self.assertEqual({"claude", "codex", "gemini"}, {runner.cli for runner in runners})
        self.assertEqual(3, len(runners))

    def test_select_conditions(self):
        self.assertEqual(["B3_gemini_solo"], [c["id"] for c in select_conditions(THREE, ["B3_gemini_solo"])])
        self.assertEqual(12, len(select_conditions(THREE, None)))
        with self.assertRaises(SystemExit):
            select_conditions(THREE, ["nope"])

    def test_condition_writer_template_replaces_the_prompt(self):
        task = BenchmarkTask("t", "livecodebench", "base", "review", {})
        adapter = mock.Mock()
        adapter.render_template.return_value = "help prompt"

        replaced = task_for_condition(
            adapter, task, {"writer_template": "harness/prompts/writer_lcb_help.txt"}
        )

        self.assertEqual("help prompt", replaced.writer_prompt)
        self.assertIs(task, task_for_condition(adapter, task, {}))


class TwelveConditionAnalysisTest(unittest.TestCase):
    def _records(self):
        records = []
        for condition in THREE:
            for task_index, task in enumerate(("t1", "t2")):
                solo = condition["reviewer"] is None
                records.append(
                    {
                        "task_id": task,
                        "condition": condition["id"],
                        "writer_model": condition["writer"]["model"],
                        "reviewer_model": None if solo else condition["reviewer"]["model"],
                        "passed": solo is False or task_index == 0,
                        "writer_passed": None if solo else task_index == 0,
                        "total_cost_usd": 1.0,
                        "writer_cost_usd": 0.5,
                        "reviewer_cost_usd": 0.5,
                        "writer_latency_s": 1.0,
                        "reviewer_latency_s": 1.0,
                        "total_latency_s": 2.0,
                        "extra": {},
                    }
                )
        return records

    def test_sid_uses_the_solo_baseline_of_each_writer(self):
        metrics = compute_metrics(self._records())

        self.assertEqual(12, len(metrics))
        self.assertEqual(0.5, metrics["C9_gemini_writes_gemini_reviews"]["sid"])
        self.assertEqual(0.5, metrics["C6_gemini_writes_claude_reviews"]["sid"])
        self.assertIsNone(metrics["B3_gemini_solo"]["sid"])

    def test_transitions_cover_all_nine_pairs(self):
        rows = compute_transitions(self._records())

        self.assertEqual(9, len(rows))
        self.assertEqual(9, sum(1 for row in rows if row["cross_condition_fixes"] == 1))

    def test_all_pairwise_comparisons_get_corrected(self):
        pairs = 12 * 11 // 2
        adjusted = benjamini_hochberg([0.5] * pairs)

        self.assertEqual(66, len(adjusted))


if __name__ == "__main__":
    unittest.main()
