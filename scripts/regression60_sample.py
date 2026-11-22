"""Step 1 of the regression-60 run: seeded sample of 60 of the paper's 116 problems.

The 116-problem list is the paper's pooled complete case
(results/processed/pooled_manifest.csv, in_complete_case == True). Source task ids
are unique across the hard and medium slices, so they are used unnamespaced.

Sampling: the 116 ids are sorted, then `random.seed(2026)` and
`random.sample(ids, len(ids))` give a fixed order. The first 60 problems in that
order that have valid original solo drafts for Claude (B1, condition A) and GPT-5.5
(B2, condition O) are kept. A problem without them is replaced by the next one in
the same seeded order. For n=116, CPython's random.sample is prefix-consistent, so
this order's first 60 equals random.sample(ids, 60) under the same seed (checked
below). Free: no model calls.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/processed/pooled_manifest.csv"
SLICE_DIRS = {"hard": ROOT / "results/raw/lcb_hard_full", "medium": ROOT / "results/raw/lcb_medium_100"}
SOLO = {"claude": "B1_claude_solo", "gpt55": "B2_gpt55_solo"}
OUT = ROOT / "experiments/task_lists/lcb_regression_60.txt"
LOG = ROOT / "results/processed/regression60_sample_log.json"
SEED, N = 2026, 60


def solo_problem(slice_name: str, task_id: str, condition: str) -> str | None:
    """Return None if the original solo record is valid, else why not."""
    path = SLICE_DIRS[slice_name] / condition / f"{task_id}__{condition}.json"
    if not path.exists():
        return f"missing {path.relative_to(ROOT)}"
    rec = json.loads(path.read_text())
    if rec.get("cli_error") or rec.get("timed_out") or rec.get("parse_failed"):
        return f"errored record {path.relative_to(ROOT)}"
    if not (rec.get("writer_artifact") or "").strip():
        return f"no draft code in {path.relative_to(ROOT)}"
    if rec.get("passed") is None:
        return f"ungraded {path.relative_to(ROOT)}"
    return None


def main() -> None:
    rows = list(csv.DictReader(MANIFEST.open()))
    slice_of = {
        r["source_task_id"]: r["slice"]
        for r in rows
        if r["in_complete_case"] == "True"
    }
    ids = sorted(slice_of)
    if len(ids) != 116:
        sys.exit(f"Expected 116 complete-case problems, found {len(ids)}")

    random.seed(SEED)
    order = random.sample(ids, len(ids))
    random.seed(SEED)
    assert random.sample(ids, N) == order[:N], "sample is not prefix-consistent"

    kept, replaced = [], []
    for task_id in order:
        if len(kept) == N:
            break
        problems = [p for c in SOLO.values() if (p := solo_problem(slice_of[task_id], task_id, c))]
        if problems:
            replaced.append({"task_id": task_id, "reasons": problems})
        else:
            kept.append(task_id)
    if len(kept) < N:
        sys.exit(f"Only {len(kept)} valid problems")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(sorted(kept)) + "\n")
    LOG.write_text(json.dumps({
        "seed": SEED, "n": N, "source": str(MANIFEST.relative_to(ROOT)),
        "seeded_order": order, "replacements": replaced,
        "slices": {t: slice_of[t] for t in sorted(kept)},
    }, indent=2))
    hard = sum(slice_of[t] == "hard" for t in kept)
    print(f"Saved {len(kept)} problems to {OUT.relative_to(ROOT)} ({hard} hard, {N - hard} medium)")
    print(f"Replacements: {len(replaced)}")
    for r in replaced:
        print(f"  {r['task_id']}: {r['reasons']}")


if __name__ == "__main__":
    main()
