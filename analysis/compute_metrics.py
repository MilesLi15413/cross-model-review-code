"""Compute PR, SID, SPD, latency, parse, and regression metrics from raw records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from harness.core.tracker import CostTracker


def load_records(checkpoint_dir: str) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    root = Path(checkpoint_dir)
    if not root.exists():
        return records

    for file_path in root.rglob("*.json"):
        if file_path.name in {"run_meta.json", "preflight.json", "report.json"}:
            continue
        payload = json.loads(file_path.read_text())
        if "task_id" in payload and "condition" in payload:
            records.append(payload)
    return records


def slice_label(checkpoint_dir: str) -> str:
    """Default slice name for a checkpoint: its directory name."""

    return Path(checkpoint_dir).name


def load_pooled_records(
    checkpoint_dirs: List[str],
    labels: Optional[List[str]] = None,
    namespace: Optional[bool] = None,
) -> List[Dict[str, object]]:
    """Load one or more checkpoints as a single record set.

    The paper pools a hard and a medium LiveCodeBench slice. Task identifiers are
    namespaced by slice before pooling so that ids from different slices can never
    be paired with each other, and each record keeps its original id in
    `source_task_id`. A single checkpoint is loaded unnamespaced, so existing
    single-run commands produce byte-identical output.
    """

    if labels is not None and len(labels) != len(checkpoint_dirs):
        raise ValueError(
            f"Got {len(labels)} labels for {len(checkpoint_dirs)} inputs; provide one label per input."
        )

    resolved_labels = labels or [slice_label(path) for path in checkpoint_dirs]
    if len(set(resolved_labels)) != len(resolved_labels):
        raise ValueError(f"Slice labels must be unique: {resolved_labels}")

    if namespace is None:
        namespace = len(checkpoint_dirs) > 1

    pooled: List[Dict[str, object]] = []
    for checkpoint_dir, label in zip(checkpoint_dirs, resolved_labels):
        records = load_records(checkpoint_dir)
        if not records:
            raise ValueError(f"No task records found in {checkpoint_dir}")
        for record in records:
            source_task_id = str(record["task_id"])
            record["slice"] = label
            record["source_task_id"] = source_task_id
            if namespace:
                record["task_id"] = f"{label}:{source_task_id}"
        pooled.extend(records)
    return pooled


def recompute_costs(records: List[Dict[str, object]], pricing_path: str) -> List[Dict[str, object]]:
    """Recompute in-memory cost fields from token counts and the pricing config."""

    tracker = CostTracker(pricing_path=pricing_path)
    for record in records:
        writer_model = record.get("writer_model")
        if writer_model:
            record["writer_cost_usd"] = tracker.compute_cost(
                str(writer_model),
                int(record.get("writer_input_tokens", 0) or 0),
                int(record.get("writer_output_tokens", 0) or 0),
                cached_input_tokens=int(record.get("writer_cached_input_tokens", 0) or 0),
                cache_creation_input_tokens=int(record.get("writer_cache_creation_input_tokens", 0) or 0),
            )

        reviewer_model = record.get("reviewer_model")
        if reviewer_model:
            record["reviewer_cost_usd"] = tracker.compute_cost(
                str(reviewer_model),
                int(record.get("reviewer_input_tokens", 0) or 0),
                int(record.get("reviewer_output_tokens", 0) or 0),
                cached_input_tokens=int(record.get("reviewer_cached_input_tokens", 0) or 0),
                cache_creation_input_tokens=int(record.get("reviewer_cache_creation_input_tokens", 0) or 0),
            )
        else:
            record["reviewer_cost_usd"] = 0.0

        record["total_cost_usd"] = float(record.get("writer_cost_usd", 0.0) or 0.0) + float(
            record.get("reviewer_cost_usd", 0.0) or 0.0
        )

    return records


def is_valid_answer(record: Dict[str, object]) -> bool:
    """Return whether a record produced a valid evaluated final answer."""

    return (
        record.get("passed") is not None
        and not bool(record.get("cli_error"))
        and not bool(record.get("timed_out"))
        and not bool(record.get("parse_failed"))
        and not bool(record.get("budget_exceeded"))
        and bool(str(record.get("final_artifact", "") or "").strip())
    )


def complete_case_task_ids(records: List[Dict[str, object]]) -> Set[str]:
    """Task IDs for which every condition has a valid evaluated answer."""

    condition_ids = {str(record["condition"]) for record in records}
    by_task: Dict[str, Dict[str, Dict[str, object]]] = defaultdict(dict)
    for record in records:
        by_task[str(record["task_id"])][str(record["condition"])] = record

    complete: Set[str] = set()
    for task_id, condition_records in by_task.items():
        if set(condition_records) != condition_ids:
            continue
        if all(is_valid_answer(record) for record in condition_records.values()):
            complete.add(task_id)
    return complete


def filter_records(records: List[Dict[str, object]], analysis_set: str) -> List[Dict[str, object]]:
    if analysis_set == "all":
        return records
    if analysis_set == "complete-case":
        complete_ids = complete_case_task_ids(records)
        return [record for record in records if str(record["task_id"]) in complete_ids]
    raise ValueError(f"Unknown analysis set: {analysis_set}")


def compute_metrics(records: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    by_condition: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        by_condition[record["condition"]].append(record)

    baselines: Dict[str, str] = {}
    for condition_id, condition_records in by_condition.items():
        if condition_records and condition_records[0].get("reviewer_model") is None:
            baselines[condition_records[0]["writer_model"]] = condition_id

    results: Dict[str, Dict[str, object]] = {}
    for condition_id, condition_records in by_condition.items():
        evaluated = [record for record in condition_records if record.get("passed") is not None]
        if not evaluated:
            continue

        n_total = len(condition_records)
        n_evaluated = len(evaluated)
        passed = sum(1 for record in evaluated if bool(record["passed"]))
        incomplete_evaluations = n_total - n_evaluated
        pass_rate = passed / n_evaluated

        avg_cost = sum(float(record.get("total_cost_usd", 0.0)) for record in condition_records) / n_total
        avg_writer_latency = sum(float(record.get("writer_latency_s", 0.0)) for record in condition_records) / n_total
        avg_reviewer_latency = sum(float(record.get("reviewer_latency_s", 0.0)) for record in condition_records) / n_total
        avg_total_latency = sum(float(record.get("total_latency_s", 0.0)) for record in condition_records) / n_total
        score_per_dollar = pass_rate / avg_cost if avg_cost > 0 else 0.0

        parse_rate = (
            sum(1 for record in condition_records if record.get("evaluated_has_solution_tag")) / n_total
        )

        results[condition_id] = {
            "condition": condition_id,
            "n_total": n_total,
            "n_evaluated": n_evaluated,
            "passed": passed,
            "incomplete_evaluations": incomplete_evaluations,
            "pass_rate": round(pass_rate, 4),
            "sid": None,
            "avg_cost_usd": round(avg_cost, 4),
            "score_per_dollar": round(score_per_dollar, 4),
            "avg_writer_latency_s": round(avg_writer_latency, 2),
            "avg_reviewer_latency_s": round(avg_reviewer_latency, 2),
            "avg_total_latency_s": round(avg_total_latency, 2),
            "parse_rate": round(parse_rate, 4),
            "parse_failures": sum(1 for record in condition_records if record.get("parse_failed")),
            "cli_errors": sum(1 for record in condition_records if record.get("cli_error")),
            "timed_out": sum(1 for record in condition_records if record.get("timed_out")),
            "writer_model": condition_records[0]["writer_model"],
            "reviewer_model": condition_records[0].get("reviewer_model"),
        }

    for condition_id, metric in results.items():
        baseline_condition = baselines.get(metric["writer_model"])
        if baseline_condition and baseline_condition in results and baseline_condition != condition_id:
            metric["sid"] = round(
                metric["pass_rate"] - results[baseline_condition]["pass_rate"],
                4,
            )

    for condition_id, condition_records in by_condition.items():
        metric = results.get(condition_id)
        if not metric or metric["reviewer_model"] is None:
            continue

        baseline_condition = baselines.get(metric["writer_model"])
        if not baseline_condition or baseline_condition not in by_condition:
            continue

        baseline_by_task = {
            record["task_id"]: record
            for record in by_condition[baseline_condition]
            if record.get("passed") is not None
        }

        # These count outcome flips against an *independently sampled* solo run of the
        # same writer, so they describe a transition between two whole pipelines. They
        # are not evidence that the reviewer fixed or broke the draft it was handed;
        # for that, see analysis/review_transitions.py, which pairs each reviewed
        # record with its own scored writer draft.
        regressions = 0
        fixes = 0
        compared = 0
        for record in condition_records:
            baseline_record = baseline_by_task.get(record["task_id"])
            if not baseline_record or record.get("passed") is None:
                continue
            if baseline_record["passed"] and not record["passed"]:
                regressions += 1
            if not baseline_record["passed"] and record["passed"]:
                fixes += 1
            compared += 1

        regression_rate = round(regressions / compared, 4) if compared else None
        metric["cross_condition_regressions"] = regressions
        metric["cross_condition_fixes"] = fixes
        metric["cross_condition_regression_rate"] = regression_rate
        # Deprecated aliases kept for one release; earlier tables used these names.
        metric["regressions"] = regressions
        metric["regression_rate"] = regression_rate

    return results


MANIFEST_FIELDS = [
    "slice",
    "source_task_id",
    "task_id",
    "condition",
    "in_complete_case",
    "valid",
    "passed",
    "writer_passed",
    "writer_eval_source",
    "reviewer_changed_artifact",
    "writer_artifact_sha256",
    "final_artifact_sha256",
    "writer_model",
    "reviewer_model",
]


def build_manifest(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Per (slice, task, condition) row describing what the pooled analysis used.

    This is the audit trail for the pooled complete case: which records exist, which
    ones were valid, which task-condition cells entered the complete-case subset, and
    (once writer drafts have been scored) the same-candidate pre/post pair.
    """

    complete_ids = complete_case_task_ids(records)
    rows: List[Dict[str, object]] = []
    for record in records:
        extra = record.get("extra") or {}
        rows.append(
            {
                "slice": record.get("slice", ""),
                "source_task_id": record.get("source_task_id", record.get("task_id")),
                "task_id": record.get("task_id"),
                "condition": record.get("condition"),
                "in_complete_case": str(record.get("task_id")) in complete_ids,
                "valid": is_valid_answer(record),
                "passed": record.get("passed"),
                "writer_passed": record.get("writer_passed"),
                "writer_eval_source": extra.get("writer_eval_source", ""),
                "reviewer_changed_artifact": extra.get("reviewer_changed_artifact"),
                "writer_artifact_sha256": extra.get("writer_artifact_sha256", ""),
                "final_artifact_sha256": extra.get("final_artifact_sha256", ""),
                "writer_model": record.get("writer_model"),
                "reviewer_model": record.get("reviewer_model"),
            }
        )
    rows.sort(key=lambda row: (str(row["slice"]), str(row["source_task_id"]), str(row["condition"])))
    return rows


def save_manifest(records: List[Dict[str, object]], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(build_manifest(records))
    print(f"Manifest saved to {output}")


def print_report(metrics: Dict[str, Dict[str, object]]) -> None:
    print(f"\n{'─' * 135}")
    print(
        f"{'Condition':<30} {'Pass':>6} {'Eval':>6} {'Inc':>5} {'PR':>6} {'SID':>7} {'$/task':>8} "
        f"{'W(s)':>7} {'R(s)':>7} {'T(s)':>7} {'SPD':>8} {'ParseR':>7} {'XRegR':>7}"
    )
    print(f"{'─' * 135}")
    for condition_id, metric in sorted(metrics.items()):
        sid = f"{metric['sid']:+.3f}" if metric["sid"] is not None else "   —  "
        regression = (
            f"{metric['cross_condition_regression_rate']:.3f}"
            if metric.get("cross_condition_regression_rate") is not None
            else "  —  "
        )
        print(
            f"{condition_id:<30} {metric['passed']:>6} {metric['n_evaluated']:>6} "
            f"{metric['incomplete_evaluations']:>5} {metric['pass_rate']:>6.3f} {sid:>7} "
            f"{metric['avg_cost_usd']:>8.4f} {metric['avg_writer_latency_s']:>7.1f} "
            f"{metric['avg_reviewer_latency_s']:>7.1f} {metric['avg_total_latency_s']:>7.1f} "
            f"{metric['score_per_dollar']:>8.2f} {metric['parse_rate']:>7.3f} {regression:>7}"
        )
    print(f"{'─' * 135}")


def save_csv(metrics: Dict[str, Dict[str, object]], output_path: str) -> None:
    fields = [
        "condition",
        "n_total",
        "n_evaluated",
        "passed",
        "incomplete_evaluations",
        "pass_rate",
        "sid",
        "avg_cost_usd",
        "score_per_dollar",
        "avg_writer_latency_s",
        "avg_reviewer_latency_s",
        "avg_total_latency_s",
        "parse_rate",
        "parse_failures",
        "cli_errors",
        "timed_out",
        "cross_condition_regression_rate",
        "cross_condition_regressions",
        "cross_condition_fixes",
        "regression_rate",
        "regressions",
        "writer_model",
        "reviewer_model",
    ]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for metric in sorted(metrics.values(), key=lambda item: item["condition"]):
            writer.writerow(metric)
    print(f"Metrics saved to {output}")


def save_json(metrics: Dict[str, Dict[str, object]], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2))
    print(f"Metrics JSON saved to {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        required=True,
        nargs="+",
        help=(
            "One or more checkpoint dirs. Passing several pools them into one analysis "
            "with task ids namespaced by slice, which is how the paper's 116-task "
            "complete case is built."
        ),
    )
    parser.add_argument(
        "--input-label",
        action="append",
        help="Slice label for each --input, in order. Defaults to the directory name.",
    )
    parser.add_argument(
        "--manifest-output",
        help="Write a per (slice, task, condition) manifest CSV of the analysed records",
    )
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--json-output", help="Output metrics JSON path")
    parser.add_argument("--report", action="store_true", help="Print metrics summary")
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

    records = load_pooled_records(args.input, args.input_label)
    if not records:
        print(f"No task records found in {args.input}")
        return

    if args.recompute_costs:
        recompute_costs(records, args.pricing_path)

    # The manifest is built from every loaded record, before the analysis-set filter,
    # so it shows what was excluded rather than only what survived.
    if args.manifest_output:
        save_manifest(records, args.manifest_output)

    records = filter_records(records, args.analysis_set)
    metrics = compute_metrics(records)
    if args.report or not args.output:
        print_report(metrics)
    if args.output:
        save_csv(metrics, args.output)
    if args.json_output:
        save_json(metrics, args.json_output)


if __name__ == "__main__":
    main()
