"""Stage 2 of the regression-60 run: review solo drafts once per reviewer.

Passing drafts measure regressions (reviewer breaks working code); failing drafts
(--drafts failing) measure fixes. Each record stores the draft's result in
`writer_passed` and the reviewed code's result in `passed`.

Plain cross-model review, no authorship label: the paper's reviewer prompt
(harness/prompts/reviewer_lcb.txt), filled exactly as the paper's pipeline fills it
(problem fields rendered by the LiveCodeBench adapter, then {writer_output} replaced
by the stored draft). Each review is a fresh one-shot CLI call; no shared session.

Drafts come from results/processed/regression60_draft_inventory.csv (passed == True).
One record per (draft, reviewer) is written to
  <checkpoint>/R_<writer>_by_<reviewer>/<task_id>__R_<writer>_by_<reviewer>.json

Safety:
- A draft with a valid saved review is never sent again (resumable).
- An invalid review (parse failure, CLI error, timeout) is retried at most
  MAX_ATTEMPTS times in total across runs; after that it stays a recorded failure.
- HTTP 402 / out of credits stops the whole run; nothing is saved for that call.
- --max-spend FAMILY=USD stops before any call that would start once that family's
  recorded spend in this checkpoint has reached the cap.
- Claude usage limits are waited out by the CLI runner's existing retry loop.

  python experiments/run_regression60_reviews.py --reviewers gemini,gpt55 --dry-run
  PYTHONPATH=external/livecodebench python experiments/run_regression60_reviews.py \
      --reviewers gemini,gpt55 --workers 3 --max-spend gemini=55 --max-spend gpt55=27
  python experiments/run_regression60_reviews.py --grade-only
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiment import get_adapter, merge_configs  # noqa: E402
from harness.core.cli_runner import CLIRunner, OutOfCreditsError, UsageLimitError  # noqa: E402
from harness.core.parser import normalize_code_artifact, parse_model_response  # noqa: E402
from harness.core.tracker import CostTracker, TaskRecord  # noqa: E402

INVENTORY = ROOT / "results/processed/regression60_draft_inventory.csv"
TEMPLATE = ROOT / "harness/prompts/reviewer_lcb.txt"
CONFIG = "experiments/configs/three_model_conditions.yaml"
BENCH_CONFIG = "experiments/configs/livecodebench.yaml"
DEFAULT_CHECKPOINT = "results/raw/regression60_reviews"
FROZEN_DIRS = ("results/raw/lcb_hard_full", "results/raw/lcb_medium_100")
MAX_ATTEMPTS = 2
CODEX_HOME = str(Path.home() / ".codex-regression60")

REVIEWERS: Dict[str, Dict[str, object]] = {
    "claude": {"cli": "claude", "model": "claude-opus-4-7", "effort": "high", "timeout_s": 30000},
    "gpt55": {"cli": "codex", "model": "gpt-5.5", "effort": "high", "timeout_s": 30000,
              "codex_home": CODEX_HOME},
    "gemini": {"cli": "gemini", "model": "gemini-3.1-pro-preview", "effort": "high", "timeout_s": 30000},
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def whitespace_normalized(code: str) -> str:
    return "\n".join(line.rstrip() for line in normalize_code_artifact(code).splitlines() if line.strip())


def diff_line_count(before: str, after: str) -> int:
    """Changed lines = added + removed lines in a unified diff (same as the demo)."""
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return sum(1 for line in lines if line[:1] in {"+", "-"} and not line.startswith(("+++", "---")))


@dataclass
class Draft:
    task_id: str
    writer: str
    source_path: str
    record: TaskRecord
    passed: bool = True


@dataclass
class Cell:
    draft: Draft
    reviewer: str
    tag: str = ""  # e.g. "__minedit" or "__rep2": a separate set of reviews

    @property
    def condition(self) -> str:
        return f"R_{self.draft.writer}_by_{self.reviewer}{self.tag}"


def load_drafts(inventory: Path, include_failing: bool = False) -> List[Draft]:
    """Passing drafts (regressions); with include_failing, failing drafts too (fixes)."""
    drafts = []
    for row in csv.DictReader(inventory.open()):
        passed = row["passed"] == "True"
        if not passed and not include_failing:
            continue
        record = TaskRecord(**json.loads((ROOT / row["source_record_path"]).read_text()))
        if not (record.writer_artifact or "").strip():
            raise SystemExit(f"No draft code in {row['source_record_path']}")
        drafts.append(Draft(row["problem_id"], row["writer"], row["source_record_path"], record, passed))
    return drafts


def build_cells(drafts: List[Draft], reviewers: List[str], tag: str = "") -> List[Cell]:
    # Ordered by reviewer (as requested), then writer, then task.
    return [Cell(d, r, tag) for r in reviewers for d in sorted(drafts, key=lambda d: (d.writer, d.task_id))]


def cell_dir(checkpoint: str, cell: Cell) -> str:
    return str(Path(checkpoint) / cell.condition)


def cell_status(tracker: CostTracker, checkpoint: str, cell: Cell) -> str:
    record = tracker.load_one(cell.draft.task_id, cell.condition, cell_dir(checkpoint, cell))
    if record is None:
        return "todo"
    if tracker.record_is_complete(record):
        return "done"
    if int(record.extra.get("attempts_total", 1)) >= MAX_ATTEMPTS:
        return "failed_final"
    return "retry"


def family_spend(tracker: CostTracker, checkpoint: str) -> Dict[str, float]:
    spend: Dict[str, float] = defaultdict(float)
    root = Path(checkpoint)
    if not root.exists():
        return spend
    for cond_dir in root.iterdir():
        if cond_dir.is_dir() and cond_dir.name.startswith("R_"):
            reviewer = cond_dir.name.rsplit("_by_", 1)[1].split("__", 1)[0]
            for record in tracker.load_all(str(cond_dir)):
                cost = float(record.extra.get("reviewer_cost_all_attempts", record.reviewer_cost_usd))
                rs = record.extra.get("reviewer_runtime_settings") or {}
                if record.reviewer_cli == "codex" and not rs.get("input_tokens_exclude_cached"):
                    # older records charged cached tokens twice; remove the double count
                    cost -= record.reviewer_cached_input_tokens * 5.0 / 1_000_000
                spend[reviewer] += max(cost, 0.0)
    return spend


def run_cell(cell: Cell, runner: CLIRunner, rendered_template: str, tracker: CostTracker, checkpoint: str,
             template_path: Path = TEMPLATE, benchmark: str = "livecodebench") -> TaskRecord:
    draft = cell.draft
    src = draft.record
    reviewer_cfg = REVIEWERS[cell.reviewer]
    # Same substitution as harness/core/pipeline.py: the raw stored draft.
    prompt = rendered_template.replace("{writer_output}", src.writer_artifact)
    out_dir = cell_dir(checkpoint, cell)
    previous = tracker.load_one(draft.task_id, cell.condition, out_dir)
    attempts_before = int(previous.extra.get("attempts_total", 0)) if previous else 0
    cost_before = float(previous.extra.get("reviewer_cost_all_attempts", 0.0)) if previous else 0.0

    record = TaskRecord(
        task_id=draft.task_id,
        condition=cell.condition,
        benchmark=benchmark,
        writer_model=src.writer_model,
        reviewer_model=str(reviewer_cfg["model"]),
        writer_effort=src.writer_effort,
        reviewer_effort=str(reviewer_cfg["effort"]),
        writer_cli=src.writer_cli,
        reviewer_cli=str(reviewer_cfg["cli"]),
        writer_cli_version=src.writer_cli_version,
        writer_started_at=src.writer_started_at,
        writer_finished_at=src.writer_finished_at,
        writer_prompt_sha256=src.writer_prompt_sha256,
        writer_artifact=src.writer_artifact,
        writer_passed=draft.passed,
        reviewer_prompt_sha256=sha256(prompt),
        extra={
            "study": "regression60",
            "source_record": draft.source_path,
            "writer_family": draft.writer,
            "reviewer_family": cell.reviewer,
            "author_label": "none",
            "template": str(template_path.resolve().relative_to(ROOT)),
            "template_sha256": sha256(template_path.read_text()),
            "run_tag": cell.tag or "main",
            "draft_sha256": sha256(normalize_code_artifact(src.writer_artifact)),
            "codex_home": "isolated" if reviewer_cfg.get("codex_home") else None,
            # Draft-side stats stay here so record totals cover this review only.
            "source_writer": {
                "latency_s": src.writer_latency_s,
                "input_tokens": src.writer_input_tokens,
                "output_tokens": src.writer_output_tokens,
                "cached_input_tokens": src.writer_cached_input_tokens,
                "cost_usd": src.writer_cost_usd,
            },
        },
    )

    paid_cost = 0.0
    for attempt in range(1, MAX_ATTEMPTS - attempts_before + 1):
        record.extra["attempts_total"] = attempts_before + attempt
        record.cli_error = record.timed_out = False
        try:
            result = runner.run(prompt, task_id=draft.task_id, condition_id=cell.condition, turn="reviewer")
        except UsageLimitError:
            raise  # includes OutOfCreditsError: stop, save nothing for this call
        except TimeoutError as exc:
            record.timed_out = True
            record.extra["reviewer_error"] = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001
            record.cli_error = True
            record.extra["reviewer_error"] = str(exc)
            continue

        parsed = parse_model_response(result.response_text)
        before = normalize_code_artifact(src.writer_artifact)
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
        if result.runtime_settings:
            record.extra["reviewer_runtime_settings"] = result.runtime_settings
        record.extra.update({
            "final_artifact_sha256": sha256(after),
            "unchanged_exact": bool(after) and after == before,
            "unchanged_whitespace": bool(after) and whitespace_normalized(after) == whitespace_normalized(before),
            "diff_lines": diff_line_count(before, after),
        })
        # Cost at API rates for this attempt (Claude's CLI reports it; others from pricing.yaml).
        attempt_cost = record.reviewer_cost_usd or tracker.compute_cost(
            record.reviewer_model, result.input_tokens, result.output_tokens,
            result.cached_input_tokens, result.cache_creation_input_tokens,
        )
        paid_cost += attempt_cost
        if not parsed.parse_failed:
            break

    tracker.finalize(record)  # writer tokens are zero here, so totals = this review only
    record.extra["reviewer_cost_all_attempts"] = cost_before + paid_cost
    tracker.save(record, out_dir)
    return record


def grade(checkpoint: str, regrade: bool = False, benchmark: str = "livecodebench") -> Dict[str, int]:
    """Grade every valid reviewed program (unchanged ones too): the paper's grader for
    LiveCodeBench, BigCodeBench's official evaluator (Docker) for BigCodeBench."""
    tracker = CostTracker()
    if benchmark == "bigcodebench":
        from harness.benchmarks import bigcodebench as bcb
        pending = []
        for cond_dir in sorted(p for p in Path(checkpoint).iterdir() if p.is_dir() and p.name.startswith("R_")):
            pending += [(r, cond_dir) for r in tracker.load_all(str(cond_dir))
                        if tracker.record_is_complete(r) and (regrade or r.passed is None)]
        if not pending:
            return {"scored": 0, "errors": 0}
        counts = bcb.grade_records([r for r, _ in pending], Path(checkpoint).name)
        for r, cond_dir in pending:
            tracker.save(r, str(cond_dir))
        return {"scored": counts.get("scored", 0), "errors": 0, "flaky": counts.get("flaky", 0)}

    from analysis.evaluate_writer_artifacts import _score_chunk
    counts = {"scored": 0, "errors": 0}
    for cond_dir in sorted(p for p in Path(checkpoint).iterdir() if p.is_dir() and p.name.startswith("R_")):
        pending = [
            r for r in tracker.load_all(str(cond_dir))
            if tracker.record_is_complete(r) and (regrade or r.passed is None)
        ]
        if not pending:
            continue
        results, errors = _score_chunk(
            [(r, r.final_artifact) for r in pending], CONFIG, BENCH_CONFIG,
            chunk_timeout_s=1800, record_timeout_s=300, label=cond_dir.name,
        )
        for r in pending:
            if r.task_id in results:
                r.passed = results[r.task_id]
                r.extra.pop("eval_error", None)
                counts["scored"] += 1
            else:
                r.extra["eval_error"] = errors.get(r.task_id, "unscored")
                counts["errors"] += 1
            tracker.save(r, str(cond_dir))
    return counts


def assert_not_frozen(checkpoint: str) -> None:
    target = Path(checkpoint).resolve()
    for frozen in FROZEN_DIRS:
        root = (ROOT / frozen).resolve()
        if target == root or root in target.parents:
            raise SystemExit(f"Refusing to write inside frozen results: {checkpoint}")
    if not Path(checkpoint).name.startswith("regression60_"):
        raise SystemExit("Checkpoint directory name must start with regression60_")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    ap.add_argument("--inventory", default=str(INVENTORY))
    ap.add_argument("--template", default=str(TEMPLATE), help="Reviewer prompt template")
    ap.add_argument("--tag", default="", help="Suffix for a separate set of reviews, e.g. __minedit")
    ap.add_argument("--reviewers", default="gemini,gpt55", help="Comma list from claude,gpt55,gemini")
    ap.add_argument("--writers", default="claude,gpt55,gemini")
    ap.add_argument("--drafts", choices=["passing", "failing", "all"], default="passing",
                    help="passing = regression study; failing = fix study; all = both")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="Run at most N pending cells (0 = all)")
    ap.add_argument("--max-spend", action="append", default=[], metavar="FAMILY=USD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--benchmark", choices=["livecodebench", "bigcodebench"], default="livecodebench")
    args = ap.parse_args()

    assert_not_frozen(args.checkpoint)
    if args.benchmark == "bigcodebench" and Path(args.template).resolve() == TEMPLATE.resolve():
        raise SystemExit("BigCodeBench needs --template harness/prompts/reviewer_bcb.txt")
    if args.grade_only:
        print(f"Grading: {grade(args.checkpoint, benchmark=args.benchmark)}")
        return

    reviewers = [r for r in args.reviewers.split(",") if r]
    writers = set(args.writers.split(","))
    unknown = [r for r in reviewers if r not in REVIEWERS]
    if unknown:
        raise SystemExit(f"Unknown reviewers {unknown}")
    caps = {k: float(v) for k, v in (item.split("=", 1) for item in args.max_spend)}

    tracker = CostTracker(str(ROOT / "experiments/configs/pricing.yaml"))
    drafts = [
        d for d in load_drafts(Path(args.inventory), include_failing=args.drafts != "passing")
        if d.writer in writers and (args.drafts != "failing" or not d.passed)
    ]
    if args.tag and not args.tag.startswith("__"):
        raise SystemExit("--tag must start with '__'")
    template_path = Path(args.template)
    cells = build_cells(drafts, reviewers, args.tag)
    status = {id(c): cell_status(tracker, args.checkpoint, c) for c in cells}
    pending = [c for c in cells if status[id(c)] in ("todo", "retry")]
    if args.limit:
        pending = pending[: args.limit]

    by_status: Dict[str, int] = defaultdict(int)
    for c in cells:
        by_status[status[id(c)]] += 1
    per_pair: Dict[str, int] = defaultdict(int)
    for c in pending:
        per_pair[c.condition] += 1
    print(f"{len(drafts)} {args.drafts} drafts x {len(reviewers)} reviewers = {len(cells)} cells: {dict(by_status)}")
    print(f"To run now: {len(pending)} {dict(sorted(per_pair.items()))}")
    print(f"Recorded spend so far (API rates): {dict(family_spend(tracker, args.checkpoint))}")
    if args.dry_run:
        return

    Path(args.checkpoint).mkdir(parents=True, exist_ok=True)
    template = template_path.read_text()
    pending_tasks = sorted({c.draft.task_id for c in pending})
    if args.benchmark == "bigcodebench":
        from harness.benchmarks import bigcodebench as bcb
        bcb_tasks = bcb.load_tasks()
        rendered = {t: bcb.render(template, bcb_tasks[t]) for t in pending_tasks}
    else:
        adapter = get_adapter("livecodebench", merge_configs(CONFIG, "livecodebench", BENCH_CONFIG))
        rendered = {t: adapter.render_template(t, template) for t in pending_tasks}

    stop = threading.Event()
    spend_lock = threading.Lock()
    spend = family_spend(tracker, args.checkpoint)
    sentinel = str(Path(args.checkpoint) / "PAUSED")

    def work(cell: Cell) -> Optional[TaskRecord]:
        if stop.is_set():
            return None
        with spend_lock:
            cap = caps.get(cell.reviewer)
            if cap is not None and spend[cell.reviewer] >= cap:
                return None
        cfg = REVIEWERS[cell.reviewer]
        runner = CLIRunner(
            cli=str(cfg["cli"]), model=str(cfg["model"]), effort=str(cfg["effort"]),
            timeout_s=int(cfg["timeout_s"]), paused_sentinel_path=sentinel,
            codex_home=cfg.get("codex_home"),
        )
        record = run_cell(cell, runner, rendered[cell.draft.task_id], tracker, args.checkpoint, template_path,
                          benchmark=args.benchmark)
        with spend_lock:
            spend[cell.reviewer] += float(record.extra.get("reviewer_cost_all_attempts", 0.0))
        return record

    hard_stop: Optional[BaseException] = None
    skipped_for_cap = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(work, c): c for c in pending}
        for n, fut in enumerate(as_completed(futures), start=1):
            try:
                rec = fut.result()
            except UsageLimitError as exc:
                stop.set()
                hard_stop = exc
                continue
            if rec is None:
                skipped_for_cap += 0 if stop.is_set() else 1
                continue
            flag = "SAME" if rec.extra.get("unchanged_exact") else f"{rec.extra.get('diff_lines', '?')}L"
            ok = "ok" if tracker.record_is_complete(rec) else "INVALID"
            print(f"  [{n}/{len(pending)}] {rec.condition} {rec.task_id} {ok} {flag} "
                  f"${rec.extra.get('reviewer_cost_all_attempts', 0):.3f} {rec.reviewer_latency_s:.0f}s", flush=True)

    print(f"Spend by reviewer in this checkpoint (API rates): "
          f"{ {k: round(v, 3) for k, v in spend.items()} }")
    if skipped_for_cap:
        print(f"Stopped {skipped_for_cap} cells at the --max-spend cap.")
    if isinstance(hard_stop, OutOfCreditsError):
        raise SystemExit(f"HARD STOP (out of credits): {hard_stop}\nNothing was saved for that call.")
    if hard_stop is not None:
        raise SystemExit(f"Stopped: {hard_stop}")
    if not args.skip_eval:
        print(f"Grading: {grade(args.checkpoint, benchmark=args.benchmark)}")


if __name__ == "__main__":
    main()
