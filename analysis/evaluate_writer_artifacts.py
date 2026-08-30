"""Score each record's stored writer draft, giving same-candidate pre/post outcomes.

The frozen runs record only the outcome of the *final* artifact. A reviewed arm and
its solo baseline were sampled independently, so comparing them measures a contrast
between two whole pipelines, not what a reviewer did to the draft it was handed.

This script closes that gap without any model calls: every record already stores the
writer draft its reviewer actually received, so re-scoring that draft with the same
LiveCodeBench evaluator yields a genuine before/after pair on one fixed candidate.
It writes `writer_passed` and never touches the frozen `passed` field.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.lcb_eval_runner import evaluate_artifact, evaluate_artifacts_batch
from harness.core.parser import normalize_code_artifact
from harness.core.tracker import CostTracker, TaskRecord


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized(text: str) -> str:
    return normalize_code_artifact(text or "")


def _iter_condition_dirs(root: Path, condition: Optional[str]) -> List[Path]:
    condition_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if condition:
        condition_dirs = [path for path in condition_dirs if path.name == condition]
    return condition_dirs


def _should_evaluate(record: TaskRecord, task_id: Optional[str], rerun: bool) -> bool:
    if task_id and record.task_id != task_id:
        return False
    if not (record.writer_artifact or "").strip():
        return False
    if record.writer_passed is not None and not rerun:
        return False
    return True


def annotate_artifacts(record: TaskRecord) -> bool:
    """Record artifact digests and whether the reviewer changed the draft.

    Returns True when the stored final artifact is the writer's draft verbatim.
    """

    writer = _normalized(record.writer_artifact)
    final = _normalized(record.final_artifact)
    record.extra["writer_artifact_sha256"] = _sha256(writer) if writer else ""
    record.extra["final_artifact_sha256"] = _sha256(final) if final else ""
    unchanged = bool(writer) and writer == final
    record.extra["reviewer_changed_artifact"] = bool(record.reviewer_model) and not unchanged
    return unchanged


def _chunks(items: Sequence, size: int) -> List[Sequence]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _score_chunk(
    pairs: Sequence[Tuple[TaskRecord, str]],
    config_path: str,
    benchmark_config_path: str,
    chunk_timeout_s: int,
    record_timeout_s: int,
    label: str,
) -> Tuple[Dict[str, bool], Dict[str, str]]:
    """Score one chunk, falling back to per-record evaluation if the chunk fails.

    A single non-terminating program would otherwise cost the whole chunk, so a chunk
    timeout retries its records individually under a tighter budget.
    """

    results: Dict[str, bool] = {}
    errors: Dict[str, str] = {}

    print(f"  {label} ({len(pairs)} records)...", end="", flush=True)
    chunk_results, error, elapsed = evaluate_artifacts_batch(
        pairs=pairs,
        config_path=config_path,
        benchmark_config_path=benchmark_config_path,
        wall_timeout_s=chunk_timeout_s,
    )

    if error is None and chunk_results is not None:
        results.update(chunk_results)
        missing = [record.task_id for record, _ in pairs if record.task_id not in chunk_results]
        print(f" done ({elapsed:.1f}s, {len(chunk_results)} scored)", flush=True)
        if not missing:
            return results, errors
        print(f"    {len(missing)} records unscored by the batch; retrying individually", flush=True)
        retry = [(record, artifact) for record, artifact in pairs if record.task_id in set(missing)]
    else:
        print(f" {error} ({elapsed:.1f}s); retrying records individually", flush=True)
        retry = list(pairs)

    for record, artifact in retry:
        passed, record_error, record_elapsed = evaluate_artifact(
            record=record,
            artifact=artifact,
            config_path=config_path,
            benchmark_config_path=benchmark_config_path,
            wall_timeout_s=record_timeout_s,
        )
        if record_error:
            errors[record.task_id] = record_error
            print(f"    {record.task_id}: {record_error} ({record_elapsed:.1f}s)", flush=True)
        else:
            results[record.task_id] = bool(passed)
            print(
                f"    {record.task_id}: {'PASS' if passed else 'FAIL'} ({record_elapsed:.1f}s)",
                flush=True,
            )

    return results, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Score the stored writer draft of each record with the LiveCodeBench "
            "evaluator so reviewer fixes and regressions can be measured on the same "
            "candidate. Requires the benchmark, but no model CLIs."
        )
    )
    parser.add_argument("--input", required=True, help="Raw checkpoint directory")
    parser.add_argument("--config", default="experiments/configs/all_conditions.yaml")
    parser.add_argument("--benchmark-config", default="experiments/configs/livecodebench.yaml")
    parser.add_argument("--condition", help="Evaluate only one condition directory")
    parser.add_argument("--task", help="Evaluate only one task id")
    parser.add_argument("--chunk-size", type=int, default=20, help="Records scored per subprocess")
    parser.add_argument(
        "--chunk-timeout-s",
        type=int,
        default=3600,
        help="Wall timeout for a chunk; on timeout its records are retried individually",
    )
    parser.add_argument(
        "--record-timeout-s",
        type=int,
        default=600,
        help="Wall timeout for an individual retry. Writer drafts are unfiltered, so keep this nonzero.",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="Re-evaluate records that already have writer_passed set",
    )
    parser.add_argument(
        "--recheck-final",
        dest="recheck_final",
        action="store_true",
        default=True,
        help=(
            "Also re-score the stored final artifact in this pass and save it as "
            "extra.final_passed_recheck, so evaluator drift between the frozen run "
            "and this one is visible instead of silent (default: on)."
        ),
    )
    parser.add_argument(
        "--no-recheck-final",
        dest="recheck_final",
        action="store_false",
        help="Skip the final-artifact recheck.",
    )
    args = parser.parse_args()

    root = Path(args.input)
    if not root.exists():
        raise SystemExit(f"Input checkpoint does not exist: {root}")

    tracker = CostTracker()
    evaluated = 0
    reused = 0
    errors = 0
    drift: List[str] = []

    for cond_dir in _iter_condition_dirs(root, args.condition):
        records = tracker.load_all(str(cond_dir))
        pending = [record for record in records if _should_evaluate(record, args.task, args.rerun)]
        print(f"{cond_dir.name}: {len(pending)} records pending writer-draft evaluation", flush=True)
        if not pending:
            continue

        to_score: List[Tuple[TaskRecord, str]] = []
        for record in pending:
            unchanged = annotate_artifacts(record)
            # A solo arm, or a reviewer that returned the draft verbatim, is already
            # scored: the stored result is this same candidate's result.
            if unchanged and record.passed is not None:
                record.writer_passed = record.passed
                record.extra["writer_eval_source"] = "final"
                record.extra.pop("writer_eval_error", None)
                tracker.save(record, str(cond_dir))
                reused += 1
            else:
                to_score.append((record, record.writer_artifact))

        print(
            f"  reused {len(pending) - len(to_score)} unchanged artifacts, "
            f"scoring {len(to_score)} writer drafts",
            flush=True,
        )

        # Scored records are written out chunk by chunk. The evaluation is long
        # enough that an interrupted run should keep the work it already paid for.
        total_chunks = (len(to_score) + args.chunk_size - 1) // args.chunk_size
        for chunk_index, chunk in enumerate(_chunks(to_score, args.chunk_size), start=1):
            writer_results, writer_errors = _score_chunk(
                pairs=chunk,
                config_path=args.config,
                benchmark_config_path=args.benchmark_config,
                chunk_timeout_s=args.chunk_timeout_s,
                record_timeout_s=args.record_timeout_s,
                label=f"writer chunk {chunk_index}/{total_chunks}",
            )

            final_results: Dict[str, bool] = {}
            final_errors: Dict[str, str] = {}
            if args.recheck_final:
                recheck_pairs = [
                    (record, record.final_artifact)
                    for record, _ in chunk
                    if (record.final_artifact or "").strip()
                ]
                if recheck_pairs:
                    final_results, final_errors = _score_chunk(
                        pairs=recheck_pairs,
                        config_path=args.config,
                        benchmark_config_path=args.benchmark_config,
                        chunk_timeout_s=args.chunk_timeout_s,
                        record_timeout_s=args.record_timeout_s,
                        label=f"final recheck chunk {chunk_index}/{total_chunks}",
                    )

            for record, _ in chunk:
                if record.task_id in writer_results:
                    record.writer_passed = writer_results[record.task_id]
                    record.extra["writer_eval_source"] = "writer_artifact"
                    record.extra.pop("writer_eval_error", None)
                    evaluated += 1
                else:
                    record.writer_passed = None
                    record.extra["writer_eval_error"] = writer_errors.get(
                        record.task_id, "lcb_eval_returned_no_result"
                    )
                    errors += 1

                if args.recheck_final:
                    if record.task_id in final_results:
                        record.extra["final_passed_recheck"] = final_results[record.task_id]
                        record.extra.pop("final_recheck_error", None)
                        if record.passed is not None and final_results[record.task_id] != record.passed:
                            drift.append(f"{record.condition}/{record.task_id}")
                    elif record.task_id in final_errors:
                        record.extra["final_recheck_error"] = final_errors[record.task_id]

                tracker.save(record, str(cond_dir))

    print(
        f"Done. writer_evaluated={evaluated} reused_unchanged={reused} "
        f"eval_errors={errors} final_recheck_disagreements={len(drift)}",
        flush=True,
    )
    if drift:
        print("Records where the final-artifact recheck disagreed with the frozen result:", flush=True)
        for item in drift:
            print(f"  {item}", flush=True)


if __name__ == "__main__":
    main()
