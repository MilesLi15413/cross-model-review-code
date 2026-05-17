"""Generate SID and Pareto figures from the aggregated metrics CSV."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


CONDITION_LABELS = {
    "C1": "Claude→GPT-5.4",
    "C2": "GPT-5.4→Claude",
    "C3": "Claude→Claude",
    "C4": "GPT-5.4→GPT-5.4",
    "B1": "Claude (solo)",
    "B2": "GPT-5.4 (solo)",
}

COLORS = {
    "C1": "#2196F3",
    "C2": "#FF5722",
    "C3": "#4CAF50",
    "C4": "#FF9800",
    "B1": "#9E9E9E",
    "B2": "#607D8B",
}


def load_metrics(path: str) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def _short_condition_id(condition: str) -> str:
    return condition.split("_", 1)[0]


def plot_sid_bar(metrics: list[dict], output_dir: str) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    two_pass = [m for m in metrics if m["reviewer_model"] and m["sid"] not in ("", "None", None)]
    if not two_pass:
        print("No two-pass conditions with SID data.")
        return

    labels = [CONDITION_LABELS.get(_short_condition_id(m["condition"]), m["condition"]) for m in two_pass]
    sids = [float(m["sid"]) for m in two_pass]
    colors = [COLORS.get(_short_condition_id(m["condition"]), "#999") for m in two_pass]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, sids, color=colors, edgecolor="white", linewidth=1.5)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Score Improvement Delta (SID)", fontsize=12)
    ax.set_title("Reviewer Improvement Over Writer-Only Baseline", fontsize=13, fontweight="bold")

    for bar, val in zip(bars, sids):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (0.005 if val >= 0 else -0.015),
            f"{val:+.3f}",
            ha="center", va="bottom" if val >= 0 else "top",
            fontsize=10, fontweight="bold",
        )

    ax.set_ylim(min(-0.05, min(sids) - 0.02), max(0.05, max(sids) + 0.05))
    plt.tight_layout()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "sid_bar.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"SID bar chart → {path}")


def plot_pareto(metrics: list[dict], output_dir: str, x_axis: str = "avg_cost_usd") -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5))

    for m in metrics:
        cond = m["condition"]
        try:
            pr = float(m["pass_rate"])
            x = float(m[x_axis])
        except (ValueError, KeyError):
            continue

        short_id = _short_condition_id(cond)
        color = COLORS.get(short_id, "#999")
        label = CONDITION_LABELS.get(short_id, cond)
        marker = "D" if cond.startswith("B") else "o"
        ax.scatter(x, pr, s=120, color=color, marker=marker, zorder=3, label=label)
        ax.annotate(
            label, (x, pr),
            textcoords="offset points", xytext=(6, 4),
            fontsize=8, color=color,
        )

    xlabel = "Avg Cost per Task (USD)" if x_axis == "avg_cost_usd" else "Avg Total Latency (s)"
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel("Pass Rate", fontsize=11)
    ax.set_title("Pass Rate vs Cost — Pareto Frontier", fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    os.makedirs(output_dir, exist_ok=True)
    suffix = "cost" if x_axis == "avg_cost_usd" else "latency"
    path = os.path.join(output_dir, f"pareto_{suffix}.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Pareto chart → {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True, help="CSV from compute_metrics.py")
    parser.add_argument("--output", default="results/processed/figures/")
    args = parser.parse_args()

    try:
        import matplotlib  # noqa
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        sys.exit(1)

    metrics = load_metrics(args.metrics)
    plot_sid_bar(metrics, args.output)
    plot_pareto(metrics, args.output, x_axis="avg_cost_usd")
    plot_pareto(metrics, args.output, x_axis="avg_total_latency_s")
    print("Done.")


if __name__ == "__main__":
    main()
