"""Logistic-regression asymmetry analysis for C1 vs C2."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, List
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.compute_metrics import load_records


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    design = np.column_stack([np.ones(len(x)), x])

    def objective(beta: np.ndarray) -> float:
        logits = design @ beta
        probabilities = np.clip(_sigmoid(logits), 1e-9, 1 - 1e-9)
        return float(-(y * np.log(probabilities) + (1 - y) * np.log(1 - probabilities)).sum())

    result = minimize(objective, np.zeros(design.shape[1]), method="BFGS")
    if not result.success:
        raise RuntimeError(f"Logistic regression did not converge: {result.message}")

    beta = result.x
    probabilities = np.clip(_sigmoid(design @ beta), 1e-9, 1 - 1e-9)
    weights = probabilities * (1 - probabilities)
    fisher = design.T @ (design * weights[:, None])
    covariance = np.linalg.inv(fisher)
    standard_errors = np.sqrt(np.diag(covariance))

    coef = float(beta[1])
    se = float(standard_errors[1])
    z_value = coef / se if se > 0 else 0.0
    p_value = float(2 * norm.sf(abs(z_value)))
    odds_ratio = math.exp(coef)
    ci_low = math.exp(coef - 1.96 * se)
    ci_high = math.exp(coef + 1.96 * se)

    return {
        "coef": round(coef, 6),
        "se": round(se, 6),
        "z": round(z_value, 6),
        "p_value": round(p_value, 6),
        "odds_ratio": round(odds_ratio, 6),
        "odds_ratio_ci_lo": round(ci_low, 6),
        "odds_ratio_ci_hi": round(ci_high, 6),
    }


def run_asymmetry_analysis(checkpoint_dir: str) -> List[Dict[str, object]]:
    records = load_records(checkpoint_dir)
    c1 = [record for record in records if str(record["condition"]).startswith("C1") and record.get("passed") is not None]
    c2 = [record for record in records if str(record["condition"]).startswith("C2") and record.get("passed") is not None]
    if not c1 or not c2:
        raise RuntimeError("Need both C1 and C2 evaluated records for asymmetry analysis.")

    paired = []
    c1_by_task = {record["task_id"]: record for record in c1}
    c2_by_task = {record["task_id"]: record for record in c2}
    shared_ids = sorted(set(c1_by_task) & set(c2_by_task))
    if not shared_ids:
        raise RuntimeError("C1 and C2 have no shared task IDs.")

    for task_id in shared_ids:
        paired.append({"task_id": task_id, "condition": "C1", "passed": bool(c1_by_task[task_id]["passed"])})
        paired.append({"task_id": task_id, "condition": "C2", "passed": bool(c2_by_task[task_id]["passed"])})

    x = np.array([1 if row["condition"] == "C2" else 0 for row in paired], dtype=float)
    y = np.array([1 if row["passed"] else 0 for row in paired], dtype=float)
    stats = _fit_logistic(x, y)

    c1_pr = sum(1 for record in c1 if record["passed"]) / len(c1)
    c2_pr = sum(1 for record in c2 if record["passed"]) / len(c2)
    return [
        {
            "comparison": "C2_vs_C1",
            "n_shared_tasks": len(shared_ids),
            "c1_pass_rate": round(c1_pr, 4),
            "c2_pass_rate": round(c2_pr, 4),
            **stats,
        }
    ]


def save_csv(rows: List[Dict[str, object]], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="results/processed/asymmetry.csv")
    args = parser.parse_args()

    rows = run_asymmetry_analysis(args.input)
    save_csv(rows, args.output)


if __name__ == "__main__":
    main()
