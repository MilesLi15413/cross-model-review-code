"""Item 2 (free): recompute the paper's per-task costs without the cached-token double count.

Frozen paper records (read only) were priced with Codex's input_tokens, which already
include cached tokens, while the cached tokens were also charged again at the cached rate.
For every GPT-5.5 turn this recomputes cost with input = input_tokens - cached_input_tokens.
All turns are priced from token counts exactly as the paper's tables were
(analysis/compute_metrics.py --recompute-costs); Claude turns are unchanged.
Output: results/processed/regression60_paper_cost_recheck.csv
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.core.tracker import CostTracker  # noqa: E402

DIRS = {"hard": "results/raw/lcb_hard_full", "medium": "results/raw/lcb_medium_100"}
OUT = ROOT / "results/processed/regression60_paper_cost_recheck.csv"
LABEL = {"B1_claude_solo": "A", "B2_gpt55_solo": "O", "C1_claude_writes_gpt55_reviews": "AO",
         "C2_gpt55_writes_claude_reviews": "OA", "C3_claude_writes_claude_reviews": "AA",
         "C4_gpt55_writes_gpt55_reviews": "OO"}


def turn(t: CostTracker, rec: dict, side: str) -> tuple[float, float]:
    """(cost as the paper's --recompute-costs priced it, cost with the double count removed)."""
    model = rec.get(f"{side}_model") or ""
    if not model:
        return 0.0, 0.0
    inp, cached = int(rec.get(f"{side}_input_tokens") or 0), int(rec.get(f"{side}_cached_input_tokens") or 0)
    out = int(rec.get(f"{side}_output_tokens") or 0)
    created = int(rec.get(f"{side}_cache_creation_input_tokens") or 0)
    as_paper = t.compute_cost(model, inp, out, cached, created)
    if not model.startswith("gpt"):
        return as_paper, as_paper
    return as_paper, t.compute_cost(model, max(inp - cached, 0), out, cached, created)


def main() -> None:
    t = CostTracker(str(ROOT / "experiments/configs/pricing.yaml"))
    rows = [r for r in csv.DictReader((ROOT / "results/processed/pooled_manifest.csv").open())
            if r["in_complete_case"] == "True"]
    out, agg = [], defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0])
    for r in rows:
        cond = r["condition"]
        rec = json.loads((ROOT / f"{DIRS[r['slice']]}/{cond}/{r['source_task_id']}__{cond}.json").read_text())
        w_old, w_new = turn(t, rec, "writer")
        v_old, v_new = turn(t, rec, "reviewer")
        recorded = w_old + v_old
        mismatch = False
        out.append({"problem_id": r["source_task_id"], "slice": r["slice"], "condition": cond,
                    "paper_total": round(recorded, 6),
                    "corrected_total": round(w_new + v_new, 6)})
        a = agg[cond]; a[0] += 1; a[1] += recorded; a[2] += w_new + v_new; a[3] += w_old + v_old; a[4] += mismatch
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(f"{'cond':<4}{'n':>5}{'paper $/task':>14}{'corrected':>11}{'change':>9}")
    for cond, lab in LABEL.items():
        n, rec, new, old, mm = agg[cond]
        print(f"{lab:<4}{n:>5}{rec/n:>14.3f}{new/n:>11.3f}{(new-rec)/rec*100:>8.0f}%")


if __name__ == "__main__":
    main()
