from __future__ import annotations

import unittest

from analysis.review_transitions import compute_transitions


def _record(task_id, condition, passed, writer_passed=None, reviewer_model=None, extra=None):
    return {
        "task_id": task_id,
        "condition": condition,
        "passed": passed,
        "writer_passed": writer_passed,
        "writer_model": "gpt-5.5",
        "reviewer_model": reviewer_model,
        "extra": extra or {},
    }


class ReviewTransitionsTest(unittest.TestCase):
    def _reviewed(self):
        return [
            # solo baseline, sampled independently of the reviewed arm
            _record("t1", "B2", False),
            _record("t2", "B2", True),
            _record("t3", "B2", True),
            _record("t4", "B2", True),
            # reviewed arm with its own scored draft
            _record("t1", "C2", True, writer_passed=False, reviewer_model="claude-opus-4-7"),
            _record("t2", "C2", False, writer_passed=True, reviewer_model="claude-opus-4-7"),
            _record("t3", "C2", True, writer_passed=True, reviewer_model="claude-opus-4-7"),
            _record("t4", "C2", False, writer_passed=False, reviewer_model="claude-opus-4-7"),
        ]

    def test_same_candidate_cells_partition_the_scored_records(self):
        row = compute_transitions(self._reviewed())[0]

        self.assertEqual("C2", row["condition"])
        self.assertEqual(1, row["reviewer_fix"])
        self.assertEqual(1, row["reviewer_regression"])
        self.assertEqual(1, row["kept_pass"])
        self.assertEqual(1, row["kept_fail"])
        self.assertEqual(4, row["n_scored"])
        self.assertEqual(
            row["n_scored"],
            row["kept_pass"] + row["reviewer_fix"] + row["reviewer_regression"] + row["kept_fail"],
        )
        self.assertEqual(0, row["net_same_candidate_change"])

    def test_cross_condition_counts_differ_from_same_candidate_counts(self):
        """The whole point of the table: the two quantities are not interchangeable."""

        row = compute_transitions(self._reviewed())[0]

        # Against the independently sampled solo arm, t2 and t4 look like regressions
        # and t1 like a fix, even though the reviewer only regressed one draft.
        self.assertEqual(2, row["cross_condition_regressions"])
        self.assertEqual(1, row["cross_condition_fixes"])
        self.assertNotEqual(row["cross_condition_regressions"], row["reviewer_regression"])

    def test_unscored_drafts_are_counted_not_silently_dropped(self):
        records = self._reviewed()
        records.append(
            _record("t5", "C2", True, writer_passed=None, reviewer_model="claude-opus-4-7")
        )

        row = compute_transitions(records)[0]

        self.assertEqual(5, row["n_records"])
        self.assertEqual(4, row["n_scored"])
        self.assertEqual(1, row["n_unscorable"])

    def test_unchanged_artifacts_are_reported(self):
        records = self._reviewed()
        records[4]["extra"] = {"reviewer_changed_artifact": False}

        row = compute_transitions(records)[0]

        self.assertEqual(1, row["unchanged_artifact"])

    def test_solo_conditions_are_not_reported(self):
        rows = compute_transitions(self._reviewed())

        self.assertEqual(["C2"], [row["condition"] for row in rows])


if __name__ == "__main__":
    unittest.main()
