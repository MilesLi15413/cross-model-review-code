from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.core.tracker import CostTracker


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
