"""BigCodeBench follow-up to the regression-60 run, writer stage.

  sample     Seeded sample of eligible tasks -> experiments/task_lists/bcb_80.txt (free)
  write      Solo drafts from each writer, one fresh CLI call per task (paid)
  grade      Grade drafts with BigCodeBench's official evaluator in Docker (free)
  inventory  Write the draft inventory the review runner reads (free)

Same models, efforts, CLIs and isolation as the regression-60 reviews (GPT-5.5 via
Codex with the isolated no-tools CODEX_HOME; Gemini with no tools; Claude Code on
Pro). Writer prompt: harness/prompts/writer_bcb.txt (the paper's writer prompt with
"competitive programmer"/"problem" replaced by "Python programmer"/"task").

Safety (same rules as the review runner):
- A draft with a valid saved record is never requested again; an invalid one is
  retried at most MAX_RUNS times in total across runs.
- HTTP 402 / out of credits stops the run; nothing is saved for that call.
- --max-spend FAMILY=USD stops before any call once that family's recorded spend in
  this checkpoint reaches the cap. --tasks N uses only the first N sampled tasks
  (the pilot is --tasks 10).

  python experiments/run_bcb_writers.py sample
  python experiments/run_bcb_writers.py write --tasks 10 --writers claude,gpt55,gemini --max-spend gemini=5 --max-spend gpt55=3
  python experiments/run_bcb_writers.py grade
  python experiments/run_bcb_writers.py inventory
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_regression60_reviews import REVIEWERS as MODELS  # noqa: E402
from harness.benchmarks import bigcodebench as bcb  # noqa: E402
from harness.core.cli_runner import CLIRunner, OutOfCreditsError, UsageLimitError  # noqa: E402
from harness.core.pipeline import BenchmarkTask, TwoPassPipeline  # noqa: E402
from harness.core.tracker import CostTracker, TaskRecord  # noqa: E402

SEED = 2026
N_TASKS = 80
TASK_LIST = ROOT / "experiments/task_lists/bcb_80.txt"
CHECKPOINT = ROOT / "results/raw/regression60_bcb_drafts"
INVENTORY = ROOT / "results/processed/regression60_bcb_draft_inventory.csv"
TEMPLATE = ROOT / "harness/prompts/writer_bcb.txt"
MAX_RUNS = 2
PRICING = str(ROOT / "experiments/configs/pricing.yaml")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample_tasks(eligible: List[str], n: int = N_TASKS, seed: int = SEED) -> List[str]:
    """Seeded shuffle of the sorted eligible ids; the first k form the k-task prefix
    (the pilot is the first 10)."""
    order = list(eligible)
    random.Random(seed).shuffle(order)
    return order[:n]


def task_ids(limit: int = 0) -> List[str]:
    ids = TASK_LIST.read_text().split()
    return ids[:limit] if limit else ids


def condition(writer: str) -> str:
    return f"W_{writer}"


def cond_dir(writer: str) -> str:
    return str(CHECKPOINT / condition(writer))


def status(tracker: CostTracker, writer: str, task_id: str) -> str:
    rec = tracker.load_one(task_id, condition(writer), cond_dir(writer))
    if rec is None:
        return "todo"
    if tracker.record_is_complete(rec):
        return "done"
    return "failed_final" if int(rec.extra.get("runs_total", 1)) >= MAX_RUNS else "retry"


def spend(tracker: CostTracker) -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for w in MODELS:
        for rec in tracker.load_all(cond_dir(w)):
            out[w] += float(rec.extra.get("writer_cost_all_runs", rec.writer_cost_usd))
    return out


def write_one(writer: str, task_id: str, task: dict, template: str, tracker: CostTracker) -> TaskRecord:
    cfg = MODELS[writer]
    runner = CLIRunner(
        cli=str(cfg["cli"]), model=str(cfg["model"]), effort=str(cfg["effort"]),
        timeout_s=int(cfg["timeout_s"]), paused_sentinel_path=str(CHECKPOINT / "PAUSED"),
        codex_home=cfg.get("codex_home"),
    )
    previous = tracker.load_one(task_id, condition(writer), cond_dir(writer))
    runs_before = int(previous.extra.get("runs_total", 0)) if previous else 0
    cost_before = float(previous.extra.get("writer_cost_all_runs", 0.0)) if previous else 0.0
    prompt = bcb.render(template, task)
    pipe = TwoPassPipeline(runner, None, tracker, condition(writer), per_task_budget_usd=100.0,
                           max_task_attempts=1)
    result = pipe.run_task(BenchmarkTask(task_id, "bigcodebench", prompt, "", {}))
    rec = result.record
    rec.extra.update({
        "study": "regression60_bcb",
        "official_task_id": task["task_id"],
        "dataset_hash": bcb.DATASET_HASH,
        "writer_family": writer,
        "template": str(TEMPLATE.relative_to(ROOT)),
        "template_sha256": sha256(template),
        "codex_home": "isolated" if cfg.get("codex_home") else None,
        "runs_total": runs_before + 1,
        "writer_cost_all_runs": cost_before + rec.writer_cost_usd,
    })
    tracker.save(rec, cond_dir(writer))
    return rec


def cmd_sample(_args) -> None:
    tasks = bcb.load_tasks()
    elig = bcb.eligible(tasks)
    chosen = sample_tasks(elig)
    if TASK_LIST.exists() and TASK_LIST.read_text().split() != chosen:
        raise SystemExit(f"{TASK_LIST} exists with a different sample; refusing to overwrite")
    TASK_LIST.write_text("\n".join(chosen) + "\n")
    print(f"{len(tasks)} tasks, {len(elig)} eligible (excluded {len(tasks) - len(elig)}: "
          f"5 failing reference solutions + network libraries); sampled {len(chosen)} with seed {SEED}")
    print("pilot (first 10):", " ".join(chosen[:10]))


def cmd_write(args) -> None:
    tracker = CostTracker(PRICING)
    tasks = bcb.load_tasks()
    template = TEMPLATE.read_text()
    writers = [w for w in args.writers.split(",") if w]
    caps = {k: float(v) for k, v in (s.split("=", 1) for s in args.max_spend)}
    ids = task_ids(args.tasks)
    cells = [(w, t) for w in writers for t in ids]
    st = {c: status(tracker, *c) for c in cells}
    pending = [c for c in cells if st[c] in ("todo", "retry")]
    counts: Dict[str, int] = defaultdict(int)
    for c in cells:
        counts[st[c]] += 1
    current = spend(tracker)
    print(f"{len(ids)} tasks x {len(writers)} writers = {len(cells)} drafts: {dict(counts)}; to run {len(pending)}")
    print(f"Recorded spend so far (API rates): { {k: round(v, 3) for k, v in current.items()} }")
    if args.dry_run or not pending:
        return

    stop = threading.Event()
    lock = threading.Lock()

    def work(cell) -> Optional[TaskRecord]:
        w, t = cell
        if stop.is_set():
            return None
        with lock:
            if w in caps and current[w] >= caps[w]:
                return None
        rec = write_one(w, t, tasks[t], template, tracker)
        with lock:
            current[w] += rec.writer_cost_usd
        return rec

    hard: Optional[BaseException] = None
    capped = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(work, c): c for c in pending}
        for n, fut in enumerate(as_completed(futs), start=1):
            try:
                rec = fut.result()
            except UsageLimitError as exc:
                stop.set()
                hard = exc
                continue
            if rec is None:
                capped += 0 if stop.is_set() else 1
                continue
            ok = "ok" if tracker.record_is_complete(rec) else "INVALID"
            print(f"  [{n}/{len(pending)}] {rec.condition} {rec.task_id} {ok} "
                  f"${rec.writer_cost_usd:.3f} {rec.writer_latency_s:.0f}s", flush=True)
    print(f"Spend (API rates): { {k: round(v, 3) for k, v in current.items()} }")
    if capped:
        print(f"Stopped {capped} drafts at the --max-spend cap.")
    if isinstance(hard, OutOfCreditsError):
        raise SystemExit(f"HARD STOP (out of credits): {hard}\nNothing was saved for that call.")
    if hard is not None:
        raise SystemExit(f"Stopped: {hard}")


def cmd_grade(args) -> None:
    tracker = CostTracker(PRICING)
    pending = []
    for w in MODELS:
        for rec in tracker.load_all(cond_dir(w)):
            if tracker.record_is_complete(rec) and (args.regrade or rec.passed is None):
                pending.append(rec)
    if not pending:
        print("Nothing to grade.")
        return
    counts = bcb.grade_records(pending, "drafts")
    for rec in pending:
        rec.writer_passed = rec.passed
        tracker.save(rec, cond_dir(rec.extra["writer_family"]))
    print(f"Graded drafts: {counts}")
    for w in MODELS:
        recs = [r for r in tracker.load_all(cond_dir(w)) if r.passed is not None]
        if recs:
            print(f"  {w}: {sum(r.passed for r in recs)}/{len(recs)} pass")


def cmd_inventory(args) -> None:
    tracker = CostTracker(PRICING)
    ids = task_ids(args.tasks)
    rows, missing = [], []
    for w in MODELS:
        for t in ids:
            rec = tracker.load_one(t, condition(w), cond_dir(w))
            if rec is None or not tracker.record_is_complete(rec) or rec.passed is None:
                missing.append(f"{w}:{t}")
                continue
            path = Path(cond_dir(w)) / f"{t}__{condition(w)}.json"
            rows.append({"problem_id": t, "writer": w, "passed": rec.passed,
                         "source_record_path": str(path.relative_to(ROOT))})
    with INVENTORY.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["problem_id", "writer", "passed", "source_record_path"])
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} drafts -> {INVENTORY.relative_to(ROOT)}; missing/ungraded: {len(missing)} {missing[:10]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample")
    w = sub.add_parser("write")
    w.add_argument("--writers", default="claude,gpt55,gemini")
    w.add_argument("--tasks", type=int, default=0, help="First N sampled tasks (0 = all)")
    w.add_argument("--workers", type=int, default=3)
    w.add_argument("--max-spend", action="append", default=[], metavar="FAMILY=USD")
    w.add_argument("--dry-run", action="store_true")
    g = sub.add_parser("grade")
    g.add_argument("--regrade", action="store_true")
    i = sub.add_parser("inventory")
    i.add_argument("--tasks", type=int, default=0)
    args = ap.parse_args()
    {"sample": cmd_sample, "write": cmd_write, "grade": cmd_grade, "inventory": cmd_inventory}[args.cmd](args)


if __name__ == "__main__":
    main()
