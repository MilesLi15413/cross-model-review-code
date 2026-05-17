from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.benchmarks.livecodebench import task_sampler


class LiveCodeBenchSamplerTest(unittest.TestCase):
    def test_sample_tasks_hard_only_from_huggingface(self):
        fake_rows = [
            {"question_id": "hard_1", "difficulty": "hard", "contest_date": "2026-01-01"},
            {"question_id": "medium_1", "difficulty": "medium", "contest_date": "2026-01-01"},
            {"question_id": "hard_2", "difficulty": "hard", "contest_date": "2026-01-02"},
            {"question_id": "easy_1", "difficulty": "easy", "contest_date": "2026-01-03"},
            {"question_id": "hard_3", "difficulty": "hard", "contest_date": "2026-01-04"},
        ]
        fake_stream = (
            (1, 1, "test.jsonl", row)
            for row in fake_rows
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "lcb_hard_2.txt"
            with mock.patch.object(task_sampler, "iter_hf_lcb_rows_with_files", return_value=fake_stream):
                selected = task_sampler.sample_tasks(
                    dataset_path="missing-dir",
                    output_path=str(output_path),
                    total=2,
                    difficulty="hard",
                )

        self.assertEqual(2, len(selected))
        self.assertTrue(all(task_id.startswith("hard_") for task_id in selected))


if __name__ == "__main__":
    unittest.main()
