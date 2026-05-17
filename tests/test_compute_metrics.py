from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analysis.compute_metrics import complete_case_task_ids, compute_metrics, filter_records, print_report, recompute_costs


class ComputeMetricsTest(unittest.TestCase):
    def test_compute_metrics_tracks_incomplete_evaluations(self):
        records = [
            {"condition": "B1", "task_id": "t1", "passed": True, "total_cost_usd": 1.0, "writer_latency_s": 1.0, "reviewer_latency_s": 0.0, "total_latency_s": 1.0, "evaluated_has_solution_tag": True, "parse_failed": False, "cli_error": False, "timed_out": False, "writer_model": "claude-opus-4-7", "reviewer_model": None},
            {"condition": "B1", "task_id": "t2", "passed": False, "total_cost_usd": 1.0, "writer_latency_s": 1.0, "reviewer_latency_s": 0.0, "total_latency_s": 1.0, "evaluated_has_solution_tag": True, "parse_failed": False, "cli_error": False, "timed_out": False, "writer_model": "claude-opus-4-7", "reviewer_model": None},
            {"condition": "B1", "task_id": "t3", "passed": None, "total_cost_usd": 0.0, "writer_latency_s": 0.0, "reviewer_latency_s": 0.0, "total_latency_s": 0.0, "evaluated_has_solution_tag": False, "parse_failed": True, "cli_error": True, "timed_out": False, "writer_model": "claude-opus-4-7", "reviewer_model": None},
        ]

        metrics = compute_metrics(records)

        self.assertEqual(3, metrics["B1"]["n_total"])
        self.assertEqual(2, metrics["B1"]["n_evaluated"])
        self.assertEqual(1, metrics["B1"]["passed"])
        self.assertEqual(1, metrics["B1"]["incomplete_evaluations"])
        self.assertEqual(0.5, metrics["B1"]["pass_rate"])

    def test_print_report_includes_pass_eval_and_incomplete_columns(self):
        metrics = {
            "B1": {
                "condition": "B1",
                "n_total": 10,
                "n_evaluated": 4,
                "passed": 3,
                "incomplete_evaluations": 6,
                "pass_rate": 0.75,
                "sid": None,
                "avg_cost_usd": 0.3457,
                "score_per_dollar": 2.17,
                "avg_writer_latency_s": 33.8,
                "avg_reviewer_latency_s": 0.0,
                "avg_total_latency_s": 33.8,
                "parse_rate": 0.3,
                "parse_failures": 7,
                "cli_errors": 6,
                "timed_out": 1,
                "writer_model": "claude-opus-4-7",
                "reviewer_model": None,
                "regression_rate": None,
            }
        }

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_report(metrics)
        output = buffer.getvalue()

        self.assertIn("Pass", output)
        self.assertIn("Eval", output)
        self.assertIn("Inc", output)
        self.assertIn("B1", output)
        self.assertIn("     3      4     6  0.750", output)

    def test_recompute_costs_uses_pricing_config(self):
        records = [
            {
                "condition": "B1",
                "task_id": "t1",
                "passed": True,
                "writer_model": "test-model",
                "reviewer_model": None,
                "writer_input_tokens": 1000,
                "writer_output_tokens": 2000,
                "writer_cached_input_tokens": 3000,
                "writer_cache_creation_input_tokens": 4000,
                "writer_cost_usd": 999.0,
                "reviewer_cost_usd": 999.0,
                "total_cost_usd": 1998.0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            pricing_path = Path(tmpdir) / "pricing.yaml"
            pricing_path.write_text(
                """
test-model:
  input_per_1m: 5.0
  output_per_1m: 25.0
  cached_input_per_1m: 0.50
  cache_creation_input_per_1m: 6.25
""".strip()
            )

            recompute_costs(records, str(pricing_path))

        expected = ((1000 * 5.0) + (2000 * 25.0) + (3000 * 0.50) + (4000 * 6.25)) / 1_000_000
        self.assertAlmostEqual(expected, records[0]["writer_cost_usd"])
        self.assertEqual(0.0, records[0]["reviewer_cost_usd"])
        self.assertAlmostEqual(expected, records[0]["total_cost_usd"])

    def test_complete_case_filter_keeps_only_tasks_valid_for_all_conditions(self):
        records = [
            {"condition": "B1", "task_id": "t1", "passed": True, "final_artifact": "x", "cli_error": False, "timed_out": False, "parse_failed": False, "budget_exceeded": False},
            {"condition": "B2", "task_id": "t1", "passed": False, "final_artifact": "x", "cli_error": False, "timed_out": False, "parse_failed": False, "budget_exceeded": False},
            {"condition": "B1", "task_id": "t2", "passed": True, "final_artifact": "x", "cli_error": False, "timed_out": False, "parse_failed": False, "budget_exceeded": False},
            {"condition": "B2", "task_id": "t2", "passed": None, "final_artifact": "", "cli_error": True, "timed_out": False, "parse_failed": True, "budget_exceeded": False},
        ]

        self.assertEqual({"t1"}, complete_case_task_ids(records))
        filtered = filter_records(records, "complete-case")

        self.assertEqual(2, len(filtered))
        self.assertEqual({"t1"}, {record["task_id"] for record in filtered})


if __name__ == "__main__":
    unittest.main()
