"""Step 8 of the regression-60 run: metrics from the graded review records. Free.

Reads results/raw/regression60_reviews/R_<writer>_by_<reviewer>/ and writes:
  results/processed/regression60_metrics.csv      one row per reviewer (+ self/cross/all)
  results/processed/regression60_by_pair.csv      one row per writer x reviewer pair
  results/processed/regression60_transitions.csv  every regression and every fix

Definitions
- Regression rate: passing drafts that fail after review / passing drafts reviewed.
- Fix rate: failing drafts that pass after review / failing drafts reviewed.
- 95% intervals: exact Clopper-Pearson.
- Unchanged: returned code identical to the draft (after removing a code fence and
  outer whitespace); a second rate ignores whitespace-only changes.
- Edit size: added + removed lines in the unified diff of draft vs returned code.
- Cost: API rates from experiments/configs/pricing.yaml for every reviewer (Claude
  runs on Pro, so its cost is the API-equivalent, not money spent).
- Invalid reviews (parse failure, CLI error, timeout, grading error) are excluded from
  the rates and counted separately.
- Sensitivity: rows with suffix "_no_tool_drafts" drop the GPT-5.5 drafts whose
  original paper run used shell or web-search tools.

Works on partial results: a pair with no graded records is simply absent.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.core.tracker import CostTracker, TaskRecord  # noqa: E402

REVIEWS = ROOT / "results/raw/regression60_reviews"
OUT = ROOT / "results/processed"
TOOL_RE = re.compile(r'"type"\s*:\s*"(command_execution|web_search|mcp_tool_call)"')
FAMILIES = ("claude", "gpt55", "gemini")


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    if n == 0:
        return (float("nan"), float("nan"))
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (float(lo), float(hi))


def tool_used_gpt_drafts(records) -> set:
    used = set()
    for r in records:
        if r.extra.get("writer_family") != "gpt55":
            continue
        src = json.loads((ROOT / r.extra["source_record"]).read_text())
        if TOOL_RE.search(src.get("writer_stdout") or ""):
            used.add(r.task_id)
    return used


def load(dirs: list[Path], tag: str) -> list[TaskRecord]:
    tracker = CostTracker()
    out = []
    for root in dirs:
        for d in sorted(root.glob("R_*_by_*")):
            name_tag = "__" + d.name.split("__", 1)[1] if "__" in d.name else ""
            if name_tag == tag:
                out.extend(tracker.load_all(str(d)))
    return out


def review_cost(r: TaskRecord, tracker: CostTracker) -> float:
    """API-rate cost of the review. Older Codex records stored input_tokens including
    cached tokens (OpenAI's convention); subtract them so cached tokens are not
    charged twice."""
    inp = r.reviewer_input_tokens
    rs = r.extra.get("reviewer_runtime_settings") or {}
    if r.reviewer_cli == "codex" and not rs.get("input_tokens_exclude_cached"):
        inp = max(inp - r.reviewer_cached_input_tokens, 0)
    one = tracker.compute_cost(r.reviewer_model, inp, r.reviewer_output_tokens,
                               r.reviewer_cached_input_tokens, r.reviewer_cache_creation_input_tokens)
    attempts = int(r.extra.get("attempts_total", 1) or 1)
    recorded_all = float(r.extra.get("reviewer_cost_all_attempts", 0) or 0)
    if attempts > 1 and r.reviewer_cli != "codex":
        return max(recorded_all, one)
    return one * (attempts if r.reviewer_cli == "codex" else 1)


def summarize(rows: list[TaskRecord], tracker: CostTracker) -> dict:
    complete = [r for r in rows if tracker.record_is_complete(r)]
    ungraded = [r for r in complete if r.passed is None and "eval_error" not in r.extra]
    valid = [r for r in complete if r.passed is not None and "eval_error" not in r.extra]
    passing = [r for r in valid if r.writer_passed]
    failing = [r for r in valid if r.writer_passed is False]
    regress = sum(1 for r in passing if not r.passed)
    fixes = sum(1 for r in failing if r.passed)
    rlo, rhi = clopper_pearson(regress, len(passing))
    flo, fhi = clopper_pearson(fixes, len(failing))
    edits = [int(r.extra.get("diff_lines", 0)) for r in valid]
    changed_edits = [e for r, e in zip(valid, edits) if not r.extra.get("unchanged_exact")]
    costs = [review_cost(r, tracker) for r in rows]
    spent = costs
    lat = [r.reviewer_latency_s for r in valid]
    n = len(valid)
    return {
        "reviews_total": len(rows),
        "reviews_valid": n,
        "reviews_invalid": len(rows) - len(complete) + sum("eval_error" in r.extra for r in complete),
        "reviews_ungraded": len(ungraded),
        "passing_reviewed": len(passing),
        "regressions": regress,
        "regression_rate": round(regress / len(passing), 4) if passing else "",
        "regression_ci_low": round(rlo, 4) if passing else "",
        "regression_ci_high": round(rhi, 4) if passing else "",
        "failing_reviewed": len(failing),
        "fixes": fixes,
        "fix_rate": round(fixes / len(failing), 4) if failing else "",
        "fix_ci_low": round(flo, 4) if failing else "",
        "fix_ci_high": round(fhi, 4) if failing else "",
        "unchanged_rate": round(sum(bool(r.extra.get("unchanged_exact")) for r in valid) / n, 4) if n else "",
        "unchanged_ws_rate": round(sum(bool(r.extra.get("unchanged_whitespace")) for r in valid) / n, 4) if n else "",
        "unchanged_rate_on_passing": round(sum(bool(r.extra.get("unchanged_exact")) for r in passing) / len(passing), 4) if passing else "",
        "edit_lines_mean": round(statistics.mean(edits), 1) if edits else "",
        "edit_lines_median": statistics.median(edits) if edits else "",
        "edit_lines_mean_when_changed": round(statistics.mean(changed_edits), 1) if changed_edits else "",
        "cost_per_review_usd": round(statistics.mean(costs), 4) if costs else "",
        "cost_total_usd": round(sum(spent), 3),
        "latency_mean_s": round(statistics.mean(lat), 1) if lat else "",
        "latency_median_s": round(statistics.median(lat), 1) if lat else "",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    import csv
    if not rows:
        return
    keys = list(rows[0])
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", nargs="+", default=[str(REVIEWS)], help="One or more review checkpoint dirs (pooled)")
    ap.add_argument("--tag", default="", help="Which set of reviews: '' (main), '__minedit', '__rep2', ...")
    ap.add_argument("--prefix", default="regression60", help="Output file prefix in results/processed")
    args = ap.parse_args()
    tracker = CostTracker(str(ROOT / "experiments/configs/pricing.yaml"))
    records = load([Path(d) for d in args.reviews], args.tag)
    tool_drafts = tool_used_gpt_drafts(records)

    def fam(r, key):
        return r.extra.get(key)

    pairs = defaultdict(list)
    for r in records:
        pairs[(fam(r, "writer_family"), fam(r, "reviewer_family"))].append(r)

    by_pair = []
    for (w, v), rows in sorted(pairs.items()):
        by_pair.append({"writer": w, "reviewer": v, "self_review": w == v, "subset": "all",
                        **summarize(rows, tracker)})
        if w == "gpt55":
            kept = [r for r in rows if r.task_id not in tool_drafts]
            by_pair.append({"writer": w, "reviewer": v, "self_review": w == v,
                            "subset": "no_tool_drafts", **summarize(kept, tracker)})

    metrics = []
    for v in FAMILIES:
        rows = [r for r in records if fam(r, "reviewer_family") == v]
        if rows:
            metrics.append({"reviewer": v, "group": "all_writers", **summarize(rows, tracker)})
            metrics.append({"reviewer": v, "group": "own_drafts",
                            **summarize([r for r in rows if fam(r, "writer_family") == v], tracker)})
            metrics.append({"reviewer": v, "group": "other_models_drafts",
                            **summarize([r for r in rows if fam(r, "writer_family") != v], tracker)})
    if records:
        metrics.append({"reviewer": "all", "group": "self_review",
                        **summarize([r for r in records if fam(r, "writer_family") == fam(r, "reviewer_family")], tracker)})
        metrics.append({"reviewer": "all", "group": "cross_review",
                        **summarize([r for r in records if fam(r, "writer_family") != fam(r, "reviewer_family")], tracker)})
        metrics.append({"reviewer": "all", "group": "all", **summarize(records, tracker)})

    transitions = []
    for r in sorted(records, key=lambda r: (r.task_id, r.condition)):
        if r.passed is None or "eval_error" in r.extra or r.writer_passed is None:
            continue
        if r.writer_passed and not r.passed:
            kind = "regression"
        elif not r.writer_passed and r.passed:
            kind = "fix"
        else:
            continue
        transitions.append({
            "type": kind, "problem_id": r.task_id, "writer": fam(r, "writer_family"),
            "reviewer": fam(r, "reviewer_family"), "edit_lines": r.extra.get("diff_lines"),
            "gpt_draft_used_tools": r.task_id in tool_drafts if fam(r, "writer_family") == "gpt55" else "",
            "eval_note": r.extra.get("eval_note", ""),
        })

    if not args.prefix.startswith("regression60"):
        raise SystemExit("--prefix must start with regression60")
    write_csv(OUT / f"{args.prefix}_by_pair.csv", by_pair)
    write_csv(OUT / f"{args.prefix}_metrics.csv", metrics)
    write_csv(OUT / f"{args.prefix}_transitions.csv", transitions)

    print(f"records: {len(records)}  GPT drafts written with tools: {sorted(tool_drafts)}")
    hdr = f"{'writer':<7}{'reviewer':<9}{'subset':<15}{'regress':>12}{'rate':>7}{'95% CI':>16}{'fix':>9}{'unch':>6}{'edit':>6}{'$/rev':>8}{'lat':>6}{'inv':>4}{'todo':>5}"
    print(hdr)
    for row in by_pair:
        ci = f"[{row['regression_ci_low']},{row['regression_ci_high']}]" if row["passing_reviewed"] else ""
        print(f"{row['writer']:<7}{row['reviewer']:<9}{row['subset']:<15}"
              f"{row['regressions']:>5}/{row['passing_reviewed']:<6}{row['regression_rate']!s:>7}{ci:>16}"
              f"{row['fixes']:>5}/{row['failing_reviewed']:<3}{row['unchanged_rate']!s:>6}"
              f"{row['edit_lines_median']!s:>6}{row['cost_per_review_usd']!s:>8}{row['latency_mean_s']!s:>6}{row['reviews_invalid']:>4}{row['reviews_ungraded']:>5}")
    print("\nby reviewer:")
    for row in metrics:
        print(f"  {row['reviewer']:<7}{row['group']:<20} regress {row['regressions']}/{row['passing_reviewed']} "
              f"[{row['regression_ci_low']},{row['regression_ci_high']}]  fix {row['fixes']}/{row['failing_reviewed']}  "
              f"unchanged {row['unchanged_rate']}  edit mean {row['edit_lines_mean']} median {row['edit_lines_median']}  "
              f"${row['cost_per_review_usd']}/review  total ${row['cost_total_usd']}")
    print(f"\ntransitions: {len(transitions)}")
    for t in transitions:
        print(f"  {t['type']:<10} {t['problem_id']:<10} {t['writer']}->{t['reviewer']}  {t['edit_lines']} lines {t['eval_note']}")


if __name__ == "__main__":
    main()
