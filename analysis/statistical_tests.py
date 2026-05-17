"""Pairwise PR tests and bootstrap CIs for SPD."""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import sys

from scipy.stats import binomtest, mstats

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.compute_metrics import compute_metrics, filter_records, load_records, recompute_costs


def mcnemar_test(pass_a: List[bool], pass_b: List[bool]) -> Tuple[int, int, float, float]:
    b = sum(1 for left, right in zip(pass_a, pass_b) if left and not right)
    c = sum(1 for left, right in zip(pass_a, pass_b) if not left and right)
    if b + c == 0:
        return b, c, 0.0, 1.0

    statistic = (abs(b - c) - 1) ** 2 / (b + c)
    p_value = binomtest(min(b, c), b + c, 0.5, alternative="two-sided").pvalue
    return b, c, round(statistic, 4), round(float(p_value), 6)


def benjamini_hochberg(p_values: List[float]) -> List[float]:
    if not p_values:
        return []
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * len(p_values)
    running = 1.0
    total = len(p_values)
    for rank, (original_index, p_value) in enumerate(reversed(indexed), start=1):
        adjusted_p = min(running, p_value * total / (total - rank + 1))
        adjusted[original_index] = round(adjusted_p, 6)
        running = adjusted_p
    return adjusted


def bootstrap_spd_ci(records: List[Dict[str, object]], resamples: int = 1000) -> Tuple[float, float]:
    rng = random.Random(42)
    samples: List[float] = []
    for _ in range(resamples):
        sample = [rng.choice(records) for _ in range(len(records))]
        evaluated = [record for record in sample if record.get("passed") is not None]
        if not evaluated:
            continue
        pass_rate = sum(1 for record in evaluated if record["passed"]) / len(evaluated)
        avg_cost = sum(float(record.get("total_cost_usd", 0.0)) for record in sample) / len(sample)
        samples.append(pass_rate / avg_cost if avg_cost > 0 else 0.0)

    if not samples:
        return 0.0, 0.0
    samples.sort()
    return round(float(mstats.mquantiles(samples, [0.025])[0]), 4), round(
        float(mstats.mquantiles(samples, [0.975])[0]),
        4,
    )


def run_tests(
    checkpoint_dir: str,
    recompute_cost_fields: bool = False,
    pricing_path: str = "experiments/configs/pricing.yaml",
    analysis_set: str = "all",
):
    records = load_records(checkpoint_dir)
    if recompute_cost_fields:
        recompute_costs(records, pricing_path)
    records = filter_records(records, analysis_set)
    metrics = compute_metrics(records)

    by_condition: Dict[str, Dict[str, Dict[str, object]]] = defaultdict(dict)
    for record in records:
        by_condition[record["condition"]][record["task_id"]] = record

    condition_ids = sorted(by_condition)
    pair_rows = []
    raw_p_values: List[float] = []

    for index, left_condition in enumerate(condition_ids):
        for right_condition in condition_ids[index + 1 :]:
            shared_ids = sorted(set(by_condition[left_condition]) & set(by_condition[right_condition]))
            if not shared_ids:
                continue
            left = [bool(by_condition[left_condition][task_id].get("passed")) for task_id in shared_ids]
            right = [bool(by_condition[right_condition][task_id].get("passed")) for task_id in shared_ids]
            a_only, b_only, statistic, p_value = mcnemar_test(left, right)
            pair_rows.append(
                {
                    "condition_a": left_condition,
                    "condition_b": right_condition,
                    "n_shared_tasks": len(shared_ids),
                    "a_only": a_only,
                    "b_only": b_only,
                    "mcnemar_chi2": statistic,
                    "p_value": p_value,
                }
            )
            raw_p_values.append(p_value)

    adjusted = benjamini_hochberg(raw_p_values)
    for row, adjusted_p in zip(pair_rows, adjusted):
        row["p_adjusted_bh"] = adjusted_p
        row["significant_005"] = adjusted_p < 0.05

    spd_rows = []
    for condition_id in condition_ids:
        condition_records = list(by_condition[condition_id].values())
        lo, hi = bootstrap_spd_ci(condition_records)
        spd_rows.append(
            {
                "condition": condition_id,
                "score_per_dollar": metrics.get(condition_id, {}).get("score_per_dollar"),
                "spd_ci_lo": lo,
                "spd_ci_hi": hi,
            }
        )

    return pair_rows, spd_rows


def save_csv(rows: List[Dict[str, object]], path: str) -> None:
    if not rows:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="results/processed/stats.csv")
    parser.add_argument("--spd-output", default="results/processed/spd_ci.csv")
    parser.add_argument(
        "--recompute-costs",
        action="store_true",
        help="Recompute costs from token counts using the pricing config instead of stored record costs",
    )
    parser.add_argument(
        "--pricing-path",
        default="experiments/configs/pricing.yaml",
        help="Pricing YAML used with --recompute-costs",
    )
    parser.add_argument(
        "--analysis-set",
        choices=["all", "complete-case"],
        default="all",
        help="Use all records or only tasks with valid answers for every condition",
    )
    args = parser.parse_args()

    pair_rows, spd_rows = run_tests(args.input, args.recompute_costs, args.pricing_path, args.analysis_set)
    save_csv(pair_rows, args.output)
    save_csv(spd_rows, args.spd_output)


if __name__ == "__main__":
    main()
