from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from analysis.compute_metrics import (
    build_manifest,
    complete_case_task_ids,
    compute_metrics,
    load_pooled_records,
    save_manifest,
)


def _record(task_id: str, condition: str, passed, **overrides):
    record = {
        "task_id": task_id,
        "condition": condition,
        "benchmark": "livecodebench",
        "passed": passed,
        "final_artifact": "print(1)",
        "writer_artifact": "print(1)",
        "cli_error": False,
        "timed_out": False,
        "parse_failed": False,
        "budget_exceeded": False,
        "total_cost_usd": 1.0,
        "writer_latency_s": 1.0,
        "reviewer_latency_s": 0.0,
        "total_latency_s": 1.0,
        "evaluated_has_solution_tag": True,
        "writer_model": "claude-opus-4-7",
        "reviewer_model": None,
    }
    record.update(overrides)
    return record


def _write_checkpoint(root: Path, records) -> str:
    for record in records:
        condition_dir = root / str(record["condition"])
        condition_dir.mkdir(parents=True, exist_ok=True)
        path = condition_dir / f"{record['task_id']}__{record['condition']}.json"
        path.write_text(json.dumps(record))
    return str(root)


class PooledLoadingTest(unittest.TestCase):
    def test_single_input_is_not_namespaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = _write_checkpoint(Path(tmp) / "lcb_hard_full", [_record("t1", "B1", True)])
            records = load_pooled_records([checkpoint])

        self.assertEqual(["t1"], [record["task_id"] for record in records])
        self.assertEqual("lcb_hard_full", records[0]["slice"])
        self.assertEqual("t1", records[0]["source_task_id"])

    def test_multiple_inputs_are_namespaced_by_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            hard = _write_checkpoint(Path(tmp) / "hard_run", [_record("t1", "B1", True)])
            medium = _write_checkpoint(Path(tmp) / "medium_run", [_record("t1", "B1", False)])
            records = load_pooled_records([hard, medium], ["hard", "medium"])

        self.assertEqual({"hard:t1", "medium:t1"}, {record["task_id"] for record in records})
        self.assertEqual({"t1"}, {record["source_task_id"] for record in records})

    def test_colliding_task_ids_do_not_merge_across_slices(self):
        """Same id in two slices must stay two tasks, not one silently overwritten."""

        with tempfile.TemporaryDirectory() as tmp:
            hard = _write_checkpoint(
                Path(tmp) / "hard_run",
                [_record("t1", "B1", True), _record("t1", "C1", True, reviewer_model="gpt-5.5")],
            )
            medium = _write_checkpoint(
                Path(tmp) / "medium_run",
                [_record("t1", "B1", False), _record("t1", "C1", False, reviewer_model="gpt-5.5")],
            )
            records = load_pooled_records([hard, medium], ["hard", "medium"])

        self.assertEqual(2, len(complete_case_task_ids(records)))
        metrics = compute_metrics(records)
        self.assertEqual(2, metrics["B1"]["n_total"])
        self.assertEqual(1, metrics["B1"]["passed"])

    def test_label_count_must_match_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = _write_checkpoint(Path(tmp) / "run", [_record("t1", "B1", True)])
            with self.assertRaises(ValueError):
                load_pooled_records([checkpoint], ["hard", "medium"])

    def test_labels_must_be_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = _write_checkpoint(Path(tmp) / "a", [_record("t1", "B1", True)])
            second = _write_checkpoint(Path(tmp) / "b", [_record("t2", "B1", True)])
            with self.assertRaises(ValueError):
                load_pooled_records([first, second], ["hard", "hard"])

    def test_missing_checkpoint_raises(self):
        with self.assertRaises(ValueError):
            load_pooled_records(["results/raw/does_not_exist"])


class CrossConditionMetricsTest(unittest.TestCase):
    def _records(self):
        return [
            _record("t1", "B1", True),
            _record("t2", "B1", True),
            _record("t3", "B1", False),
            _record("t1", "C1", False, reviewer_model="gpt-5.5"),
            _record("t2", "C1", True, reviewer_model="gpt-5.5"),
            _record("t3", "C1", True, reviewer_model="gpt-5.5"),
        ]

    def test_cross_condition_counts_are_reported_under_explicit_names(self):
        metrics = compute_metrics(self._records())

        self.assertEqual(1, metrics["C1"]["cross_condition_regressions"])
        self.assertEqual(1, metrics["C1"]["cross_condition_fixes"])
        self.assertAlmostEqual(1 / 3, metrics["C1"]["cross_condition_regression_rate"], places=4)

    def test_legacy_regression_aliases_still_present(self):
        metrics = compute_metrics(self._records())

        self.assertEqual(
            metrics["C1"]["cross_condition_regressions"], metrics["C1"]["regressions"]
        )
        self.assertEqual(
            metrics["C1"]["cross_condition_regression_rate"], metrics["C1"]["regression_rate"]
        )


class ManifestTest(unittest.TestCase):
    def test_manifest_marks_complete_case_membership(self):
        records = [
            _record("t1", "B1", True),
            _record("t1", "C1", True, reviewer_model="gpt-5.5"),
            _record("t2", "B1", True),
            _record("t2", "C1", None, reviewer_model="gpt-5.5", parse_failed=True, final_artifact=""),
        ]

        rows = {(row["task_id"], row["condition"]): row for row in build_manifest(records)}

        self.assertTrue(rows[("t1", "B1")]["in_complete_case"])
        self.assertFalse(rows[("t2", "B1")]["in_complete_case"])
        self.assertTrue(rows[("t1", "C1")]["valid"])
        self.assertFalse(rows[("t2", "C1")]["valid"])

    def test_manifest_csv_carries_same_candidate_columns(self):
        records = [
            _record(
                "t1",
                "C1",
                True,
                reviewer_model="gpt-5.5",
                writer_passed=False,
                extra={"writer_eval_source": "writer_artifact", "reviewer_changed_artifact": True},
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "manifest.csv"
            save_manifest(records, str(output))
            rows = list(csv.DictReader(output.open()))

        self.assertEqual("False", rows[0]["writer_passed"])
        self.assertEqual("True", rows[0]["passed"])
        self.assertEqual("writer_artifact", rows[0]["writer_eval_source"])


if __name__ == "__main__":
    unittest.main()
