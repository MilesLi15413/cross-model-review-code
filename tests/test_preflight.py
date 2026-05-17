from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.run_experiment import _preflight_report_has_effort, maybe_run_preflight
from harness.core.preflight import build_preflight_runners


class PreflightTest(unittest.TestCase):
    def test_build_preflight_runners_dedupes_by_effort(self):
        conditions = [
            {
                "id": "C1",
                "writer": {"cli": "codex", "model": "gpt-5.4", "effort": "medium"},
                "reviewer": None,
            },
            {
                "id": "C2",
                "writer": {"cli": "codex", "model": "gpt-5.4", "effort": "high"},
                "reviewer": None,
            },
        ]

        runners = build_preflight_runners(conditions)

        self.assertEqual(2, len(runners))
        self.assertEqual({"medium", "high"}, {runner.effort for runner in runners})

    def test_preflight_report_requires_effort_metadata(self):
        self.assertFalse(_preflight_report_has_effort({"checks": [{"cli": "codex", "model": "gpt-5.4"}]}))
        self.assertTrue(
            _preflight_report_has_effort(
                {"checks": [{"cli": "codex", "model": "gpt-5.4", "effort": "medium"}]}
            )
        )

    def test_maybe_run_preflight_refreshes_stale_cached_report(self):
        conditions = [
            {
                "id": "B2",
                "writer": {"cli": "codex", "model": "gpt-5.4", "effort": "medium"},
                "reviewer": None,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            preflight_path = Path(tmpdir) / "preflight.json"
            preflight_path.write_text(json.dumps({"checks": [{"cli": "codex", "model": "gpt-5.4"}]}))

            fresh_report = {
                "checked_at": "2026-04-25T00:00:00Z",
                "checks": [{"cli": "codex", "model": "gpt-5.4", "effort": "medium"}],
            }

            with mock.patch("experiments.run_experiment.run_preflight", return_value=fresh_report) as run_mock:
                report = maybe_run_preflight(tmpdir, conditions, skip_preflight=False)

            self.assertEqual(fresh_report, report)
            run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
