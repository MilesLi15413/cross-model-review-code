"""Reviewer-only authorship-label study on frozen, already graded writer drafts.

How to run (no flags beyond these are needed; --dry-run makes no model calls):
  PYTHONPATH=external/livecodebench python experiments/run_label_study.py \
    --manifest experiments/configs/label_demo_drafts.yaml \
    --checkpoint results/raw/label_demo --stop-on-limit --dry-run
Continue a stopped run with: --resume results/raw/label_demo
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import random
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiment import get_adapter, maybe_run_preflight, merge_configs
from harness.core.cli_runner import CLIRunner, UsageLimitError
from harness.core.parser import normalize_code_artifact, parse_issues, parse_model_response
from harness.core.tracker import CostTracker, TaskRecord

FAMILY_LABELS = {"claude": "Claude", "gpt": "GPT/Codex", "gemini": "Gemini"}
CLI_FAMILIES = {"claude": "claude", "codex": "gpt", "gemini": "gemini"}
ARMS = ("true", "false", "none")
FROZEN_DIRS = ("results/raw/lcb_hard_full", "results/raw/lcb_medium_100")
MAX_ATTEMPTS = 2


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Draft:
    task_id: str
    family: str
    code: str
    passed: bool
    source: TaskRecord
    source_path: str
    family_index: int = 0


def family_of(record: TaskRecord) -> str:
    if record.writer_cli in CLI_FAMILIES:
        return CLI_FAMILIES[record.writer_cli]
    model = record.writer_model.lower()
    for prefix, family in (("claude", "claude"), ("gpt", "gpt"), ("gemini", "gemini")):
        if model.startswith(prefix):
            return family
    raise ValueError(f"Cannot tell the model family of {record.writer_model!r}")


def load_draft(path: str) -> Draft:
    payload = json.loads(Path(path).read_text())
    record = TaskRecord(**payload)
    code = record.writer_artifact or ""
    passed = record.writer_passed
    if passed is None and record.reviewer_model is None:
        passed = record.passed
    if not code.strip() or passed is None:
        raise ValueError(f"{path} has no graded writer draft")
    return Draft(record.task_id, family_of(record), code, bool(passed), record, path)


def load_manifest(path: str) -> List[Draft]:
    entries = (yaml.safe_load(Path(path).read_text()) or {}).get("drafts", [])
    drafts = [load_draft(str(entry["record"])) for entry in entries]
    seen = set()
    for draft in drafts:
        key = (draft.task_id, draft.family)
        if key in seen:
            raise ValueError(f"Duplicate draft for {key}")
        seen.add(key)

    by_family: Dict[str, List[Draft]] = defaultdict(list)
    for draft in drafts:
        by_family[draft.family].append(draft)
    for family_drafts in by_family.values():
        for index, draft in enumerate(sorted(family_drafts, key=lambda item: item.task_id)):
            draft.family_index = index
    return drafts


def false_family(seed: int, writer_family: str, reviewer_family: str, family_index: int) -> str:
    """Rotate through the two wrong families so each is used equally often."""

    others = sorted(family for family in FAMILY_LABELS if family != writer_family)
    offset = int(sha256(f"{seed}|{writer_family}|{reviewer_family}"), 16)
    return others[(offset + family_index) % len(others)]


def labeled_family(arm: str, draft: Draft, reviewer_family: str, seed: int) -> Optional[str]:
    if arm == "true":
        return draft.family
    if arm == "false":
        return false_family(seed, draft.family, reviewer_family, draft.family_index)
    return None


def label_text(family: Optional[str]) -> str:
    return f"This code was written by {FAMILY_LABELS[family]}." if family else ""


def build_prompt(template_with_problem: str, draft_code: str, label: str, evidence: str = "") -> str:
    """Fill the label and evidence first, so draft text cannot collide with a placeholder."""

    labeled = (
        template_with_problem.replace("{author_label}", label)
        if label
        else template_with_problem.replace("{author_label}\n", "")
    )
    return labeled.replace("{evidence}", evidence).replace("{writer_output}", draft_code)


def diff_line_count(before: str, after: str) -> int:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return sum(
        1
        for line in lines
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    )


def build_cells(drafts: List[Draft], reviewers: List[Dict[str, object]], seed: int) -> List[Dict[str, object]]:
    cells = []
    for draft in drafts:
        for reviewer in reviewers:
            for arm in ARMS:
                family = labeled_family(arm, draft, str(reviewer["family"]), seed)
                cells.append(
                    {
                        "condition": f"L_{draft.family}_by_{reviewer['family']}_{arm}",
                        "draft": draft,
                        "reviewer": reviewer,
                        "arm": arm,
                        "labeled_family": family,
                    }
                )
    random.Random(seed).shuffle(cells)
    return cells


def new_record(cell: Dict[str, object], label: str, evidence_mode: str, evidence: str, seed: int) -> TaskRecord:
    draft: Draft = cell["draft"]
    reviewer = cell["reviewer"]
    source = draft.source
    reviewer_family = str(reviewer["family"])
    labeled = cell["labeled_family"]
    return TaskRecord(
        task_id=draft.task_id,
        condition=str(cell["condition"]),
        benchmark="livecodebench",
        writer_model=source.writer_model,
        reviewer_model=str(reviewer["model"]),
        writer_effort=source.writer_effort,
        reviewer_effort=reviewer.get("effort"),
        writer_cli=source.writer_cli,
        reviewer_cli=str(reviewer["cli"]),
        writer_cli_version=source.writer_cli_version,
        writer_prompt_sha256=source.writer_prompt_sha256,
        writer_artifact=draft.code,
        writer_passed=draft.passed,
        extra={
            "source_record": draft.source_path,
            "draft_sha256": sha256(normalize_code_artifact(draft.code)),
            "writer_family": draft.family,
            "reviewer_family": reviewer_family,
            "label_arm": cell["arm"],
            "labeled_family": labeled,
            "label_text": label,
            "label_relation": (
                "none" if labeled is None else "self" if labeled == reviewer_family else "other"
            ),
            "label_seed": seed,
            "evidence_mode": evidence_mode,
            "evidence_sha256": sha256(evidence),
        },
    )


def run_cell(
    cell: Dict[str, object],
    runner: CLIRunner,
    template: str,
    tracker: CostTracker,
    checkpoint_dir: str,
    evidence_mode: str,
    evidence: str,
    seed: int,
) -> TaskRecord:
    draft: Draft = cell["draft"]
    label = label_text(cell["labeled_family"])
    prompt = build_prompt(template, draft.code, label, evidence)
    record = new_record(cell, label, evidence_mode, evidence, seed)
    record.reviewer_prompt_sha256 = sha256(prompt)
    record.extra["template_sha256"] = sha256(template)
    condition_dir = str(Path(checkpoint_dir) / record.condition)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        record.extra["attempt_count"] = attempt
        record.cli_error = record.timed_out = False
        try:
            result = runner.run(prompt, task_id=draft.task_id, condition_id=record.condition, turn="reviewer")
        except UsageLimitError:
            raise
        except TimeoutError as exc:
            record.timed_out = True
            record.extra["reviewer_error"] = str(exc)
            continue
        except Exception as exc:
            record.cli_error = True
            record.extra["reviewer_error"] = str(exc)
            continue

        parsed = parse_model_response(result.response_text)
        issues = parse_issues(result.response_text)
        before = normalize_code_artifact(draft.code)
        after = normalize_code_artifact(parsed.artifact)
        record.reviewer_cli_version = result.cli_version
        record.reviewer_started_at = result.started_at
        record.reviewer_finished_at = result.finished_at
        record.reviewer_latency_s = result.duration_s
        record.reviewer_input_tokens = result.input_tokens
        record.reviewer_output_tokens = result.output_tokens
        record.reviewer_cached_input_tokens = result.cached_input_tokens
        record.reviewer_cache_creation_input_tokens = result.cache_creation_input_tokens
        record.reviewer_cost_usd = result.cost_usd or 0.0
        record.reviewer_stdout = result.raw_stdout
        record.reviewer_stderr = result.raw_stderr
        record.reviewer_artifact = parsed.artifact
        record.reviewer_parse_method = parsed.parse_method
        record.reviewer_has_solution_tag = parsed.has_solution_tag
        record.final_artifact = parsed.artifact
        record.evaluated_turn = "reviewer"
        record.evaluated_parse_method = parsed.parse_method
        record.evaluated_has_solution_tag = parsed.has_solution_tag
        record.parse_failed = parsed.parse_failed
        record.extra.update(
            {
                "final_artifact_sha256": sha256(after),
                "draft_unchanged": sha256(after) == record.extra["draft_sha256"],
                "diff_lines": diff_line_count(before, after),
                "issues_status": issues["status"],
                "issue_count": issues["count"],
                "issues": issues["issues"],
            }
        )
        if result.runtime_settings:
            record.extra["reviewer_runtime_settings"] = result.runtime_settings
        if not parsed.parse_failed:
            break

    tracker.finalize(record)
    tracker.save(record, condition_dir)
    return record


def grade_records(checkpoint_dir: str, config_path: str, benchmark_config_path: str) -> Dict[str, int]:
    """Grade each final program on the hidden tests through the fresh-interpreter evaluator."""

    from analysis.evaluate_writer_artifacts import _score_chunk

    tracker = CostTracker()
    counts = {"reused": 0, "scored": 0, "errors": 0}
    for condition_dir in sorted(path for path in Path(checkpoint_dir).iterdir() if path.is_dir()):
        pending = []
        for record in tracker.load_all(str(condition_dir)):
            if record.passed is not None or not tracker.record_is_complete(record):
                continue
            if record.extra.get("draft_unchanged"):
                record.passed = record.writer_passed
                tracker.save(record, str(condition_dir))
                counts["reused"] += 1
            else:
                pending.append((record, record.final_artifact))
        if not pending:
            continue
        results, errors = _score_chunk(
            pending,
            config_path,
            benchmark_config_path,
            chunk_timeout_s=900,
            record_timeout_s=300,
            label=condition_dir.name,
        )
        for record, _ in pending:
            if record.task_id in results:
                record.passed = results[record.task_id]
                counts["scored"] += 1
            else:
                record.extra["eval_error"] = errors.get(record.task_id, "unscored")
                counts["errors"] += 1
            tracker.save(record, str(condition_dir))
    return counts


def assert_not_frozen(checkpoint_dir: str) -> None:
    target = Path(checkpoint_dir).resolve()
    for frozen in FROZEN_DIRS:
        root = (ROOT / frozen).resolve()
        if target == root or root in target.parents:
            raise SystemExit(f"Refusing to write inside frozen results: {checkpoint_dir}")


def evidence_for(
    drafts: List[Draft],
    evidence_mode: str,
    config_path: str,
    benchmark_config_path: str,
    feedback_builder: Optional[Callable[[Draft], str]] = None,
) -> Dict[str, str]:
    if evidence_mode == "none":
        return {sha256(draft.code): "" for draft in drafts}

    from analysis.public_test_feedback import format_feedback, run_public_tests

    def default_builder(draft: Draft) -> str:
        return format_feedback(
            run_public_tests(draft.task_id, draft.code, config_path, benchmark_config_path)
        )

    builder = feedback_builder or default_builder
    return {sha256(draft.code): builder(draft) for draft in drafts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", help="YAML listing the source records of the drafts")
    parser.add_argument("--checkpoint", help="Output directory for reviewer records")
    parser.add_argument("--config", default="experiments/configs/label_study.yaml")
    parser.add_argument("--benchmark-config", default="experiments/configs/livecodebench.yaml")
    parser.add_argument("--evidence", choices=["none", "public_tests"], default="none")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--stop-on-limit", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="List the planned calls; call no model")
    parser.add_argument("--resume", metavar="CHECKPOINT_DIR")
    args = parser.parse_args()

    if args.resume:
        meta = json.loads((Path(args.resume) / "run_meta.json").read_text())
        args.checkpoint = args.resume
        args.manifest = meta["manifest"]
        args.config = meta["config"]
        args.benchmark_config = meta["benchmark_config"]
        args.evidence = meta["evidence"]
        args.stop_on_limit = meta["stop_on_limit"]
        for paused in Path(args.resume).glob("PAUSED"):
            paused.unlink()
    if not args.manifest or not args.checkpoint:
        parser.error("--manifest and --checkpoint are required (or use --resume)")

    assert_not_frozen(args.checkpoint)
    study = yaml.safe_load(Path(args.config).read_text())
    seed = int(study["label_seed"])
    reviewers = study["reviewers"]
    template = Path(study["template"]).read_text()
    drafts = load_manifest(args.manifest)
    cells = build_cells(drafts, reviewers, seed)
    tracker = CostTracker(pricing_path=study["pricing_path"])

    if args.dry_run:
        counts: Dict[str, int] = defaultdict(int)
        for cell in cells:
            counts[f"{cell['reviewer']['family']} reviews"] += 1
            counts[f"{cell['arm']} arm"] += 1
        print(f"{len(drafts)} drafts, {len(cells)} reviewer calls planned: {dict(sorted(counts.items()))}")
        for draft in drafts:
            print(f"  {draft.family:<7} {draft.task_id:<10} {'PASS' if draft.passed else 'FAIL'}")
        return

    Path(args.checkpoint).mkdir(parents=True, exist_ok=True)
    (Path(args.checkpoint) / "run_meta.json").write_text(
        json.dumps(
            {
                "manifest": args.manifest,
                "config": args.config,
                "benchmark_config": args.benchmark_config,
                "evidence": args.evidence,
                "stop_on_limit": args.stop_on_limit,
                "label_seed": seed,
                "reviewers": reviewers,
                "template": study["template"],
                "template_sha256": sha256(template),
            },
            indent=2,
        )
    )
    maybe_run_preflight(
        args.checkpoint,
        [{"id": str(reviewer["family"]), "writer": reviewer, "reviewer": None} for reviewer in reviewers],
        args.skip_preflight,
    )

    config = merge_configs(args.config, "livecodebench", args.benchmark_config)
    adapter = get_adapter("livecodebench", config)
    task_ids = sorted({draft.task_id for draft in drafts})
    templates = {task_id: adapter.render_template(task_id, template) for task_id in task_ids}
    evidence = evidence_for(drafts, args.evidence, args.config, args.benchmark_config)
    pending = [
        cell
        for cell in cells
        if not tracker.is_done(
            cell["draft"].task_id,
            str(cell["condition"]),
            str(Path(args.checkpoint) / str(cell["condition"])),
        )
    ]
    print(f"{len(cells) - len(pending)} cells already done, {len(pending)} to run.")

    stop = threading.Event()
    sentinel = str(Path(args.checkpoint) / "PAUSED")

    def work(cell: Dict[str, object]) -> Optional[TaskRecord]:
        if stop.is_set():
            return None
        reviewer = cell["reviewer"]
        runner = CLIRunner(
            cli=str(reviewer["cli"]),
            model=str(reviewer["model"]),
            effort=reviewer.get("effort"),
            timeout_s=int(reviewer.get("timeout_s", 300)),
            paused_sentinel_path=sentinel,
            stop_on_limit=args.stop_on_limit,
        )
        draft: Draft = cell["draft"]
        return run_cell(
            cell,
            runner,
            templates[draft.task_id],
            tracker,
            args.checkpoint,
            args.evidence,
            evidence[sha256(draft.code)],
            seed,
        )

    limit_error: Optional[UsageLimitError] = None
    total_cost = 0.0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(work, cell): cell for cell in pending}
        for done, future in enumerate(as_completed(futures), start=1):
            cell = futures[future]
            try:
                record = future.result()
            except UsageLimitError as exc:
                stop.set()
                limit_error = exc
                continue
            if record is None:
                continue
            total_cost += record.total_cost_usd
            print(
                f"  [{done}/{len(pending)}] {record.condition} {record.task_id} "
                f"${record.total_cost_usd:.3f} {record.reviewer_latency_s:.0f}s "
                f"parse={record.reviewer_parse_method or 'none'}",
                flush=True,
            )

    print(f"Reviewer spend at API rates this session: ${total_cost:.2f}")
    if limit_error:
        raise SystemExit(
            f"{limit_error}\nFinished cells are saved. After the limit resets, continue with:\n"
            f"  python experiments/run_label_study.py --resume {args.checkpoint}"
        )
    if not args.skip_eval:
        print(f"Grading: {grade_records(args.checkpoint, args.config, args.benchmark_config)}")


if __name__ == "__main__":
    main()
