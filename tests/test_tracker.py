from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json

from harness.core.tracker import CostTracker, TaskRecord


class CostTrackerTest(unittest.TestCase):
    def test_compute_cost_uses_cache_creation_rate(self):
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
            tracker = CostTracker(str(pricing_path))

            cost = tracker.compute_cost(
                "test-model",
                input_tokens=1000,
                output_tokens=2000,
                cached_input_tokens=3000,
                cache_creation_input_tokens=4000,
            )

        expected = ((1000 * 5.0) + (2000 * 25.0) + (3000 * 0.50) + (4000 * 6.25)) / 1_000_000
        self.assertAlmostEqual(expected, cost)

    def test_compute_cost_applies_long_context_multiplier(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pricing_path = Path(tmpdir) / "pricing.yaml"
            pricing_path.write_text(
                """
test-model:
  input_per_1m: 5.0
  output_per_1m: 30.0
  cached_input_per_1m: 0.50
  long_context_threshold_tokens: 272000
  long_context_input_multiplier: 2.0
  long_context_output_multiplier: 1.5
""".strip()
            )
            tracker = CostTracker(str(pricing_path))

            cost = tracker.compute_cost(
                "test-model",
                input_tokens=273000,
                output_tokens=1000,
                cached_input_tokens=0,
            )

        expected = ((273000 * 10.0) + (1000 * 45.0)) / 1_000_000
        self.assertAlmostEqual(expected, cost)


if __name__ == "__main__":
    unittest.main()


class WriterPassedFieldTest(unittest.TestCase):
    def test_writer_passed_round_trips_through_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CostTracker()
            record = TaskRecord(
                task_id="t1",
                condition="C2",
                benchmark="livecodebench",
                writer_model="gpt-5.5",
                reviewer_model="claude-opus-4-7",
                passed=True,
                writer_passed=False,
                final_artifact="print(1)",
            )
            tracker.save(record, tmpdir)
            loaded = tracker.load_one("t1", "C2", tmpdir)

        self.assertFalse(loaded.writer_passed)
        self.assertTrue(loaded.passed)

    def test_records_written_before_the_field_existed_still_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy = {
                "task_id": "t1",
                "condition": "B1",
                "benchmark": "livecodebench",
                "writer_model": "claude-opus-4-7",
                "reviewer_model": None,
                "passed": True,
            }
            Path(tmpdir, "t1__B1.json").write_text(json.dumps(legacy))
            loaded = CostTracker().load_one("t1", "B1", tmpdir)

        self.assertIsNone(loaded.writer_passed)
        self.assertTrue(loaded.passed)
