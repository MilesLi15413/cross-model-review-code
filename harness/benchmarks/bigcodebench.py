"""BigCodeBench support for the regression-60 follow-up (instruct split, full set).

Tasks come from the official evaluation image (bigcodebench 0.2.4, dataset hash
acf4f1debe64a10c1a0bf6d4906245b2), exported once to external/bcb_work/bcb_full.json
by external/bcb_work/export_tasks.py. Grading runs BigCodeBench's own evaluator
inside that image, exactly as its leaderboard does (calibrated: the task's code
prompt is prepended), with the fixed 20 s per-task limit used when reference
timings are not computed (--no_gt), which is also how the grader check was run.

Local task ids replace the slash: "BigCodeBench/16" -> "bcb_16" (file-name safe).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "external/bcb_work"
TASKS_PATH = WORK / "bcb_full.json"
IMAGE = "bigcodebench/bigcodebench-evaluate@sha256:a3cd34ec3840a49d6b7afb240f4bdd47c350bc5991043fd0a91773830f7cd405"
DATASET_HASH = "acf4f1debe64a10c1a0bf6d4906245b2"
DOCKER_PATHS = ("/usr/local/bin", "/Applications/Docker.app/Contents/Resources/bin")

# Reference solutions that failed in both grader-check runs (2 of 2, identical).
GT_FAILING = {"BigCodeBench/1005", "BigCodeBench/205", "BigCodeBench/363",
              "BigCodeBench/590", "BigCodeBench/917"}
# Tasks importing these may touch the live internet; excluded so no result hinges
# on a download or a remote server.
NETWORK_LIBS = {"requests", "urllib", "socket", "smtplib", "ftplib", "http", "mechanize",
                "wikipedia", "selenium", "geopy", "ssl", "sendgrid", "python_http_client",
                "urllib3", "httpx", "aiohttp", "paramiko"}


def to_local(task_id: str) -> str:
    return "bcb_" + task_id.split("/", 1)[1]


def to_official(local_id: str) -> str:
    return "BigCodeBench/" + local_id.split("_", 1)[1]


def load_tasks(path: Path = TASKS_PATH) -> Dict[str, dict]:
    """Official task dicts keyed by local id."""
    payload = json.loads(Path(path).read_text())
    if payload.get("hash") != DATASET_HASH:
        raise SystemExit(f"Unexpected BigCodeBench dataset hash {payload.get('hash')}")
    return {to_local(tid): t for tid, t in payload["tasks"].items()}


def task_libs(task: dict) -> List[str]:
    libs = task["libs"]
    if isinstance(libs, str):
        import ast
        libs = ast.literal_eval(libs)
    return list(libs)


def eligible(tasks: Dict[str, dict]) -> List[str]:
    """Sorted local ids: reference solution passes, no network libraries."""
    keep = []
    for local_id, t in tasks.items():
        if t["task_id"] in GT_FAILING:
            continue
        if NETWORK_LIBS & set(task_libs(t)):
            continue
        keep.append(local_id)
    return sorted(keep, key=lambda s: int(s.split("_", 1)[1]))


def render(template: str, task: dict) -> str:
    """Fill a prompt template. The instruct prompt already ends with the required
    function header, so {starter_code} is empty."""
    return template.replace("{problem}", task["instruct_prompt"].strip()).replace("{starter_code}", "")


def _docker() -> str:
    found = shutil.which("docker")
    if found:
        return found
    for d in DOCKER_PATHS:
        if (Path(d) / "docker").exists():
            return str(Path(d) / "docker")
    raise SystemExit("docker not found: start Docker Desktop")


def _grade_once(items: Sequence[Tuple[str, str]], label: str) -> List[dict]:
    """One evaluator pass over items (local_id, code). Returns per-item
    {"status", "detail"} in input order. Several items may share a task id."""
    run_dir = WORK / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"{label}_{uuid.uuid4().hex[:8]}"  # fresh name: the evaluator reuses old result files
    samples = run_dir / f"{name}.jsonl"
    with samples.open("w") as fh:
        for local_id, code in items:
            fh.write(json.dumps({"task_id": to_official(local_id), "solution": code}) + "\n")
    selected = ",".join(sorted({to_official(i) for i, _ in items}))
    log = run_dir / f"{name}.log"
    cmd = [_docker(), "run", "--rm", "--platform", "linux/amd64", "-v", f"{WORK}:/app", IMAGE,
           "--execution", "local", "--split", "instruct", "--subset", "full",
           "--samples", f"/app/runs/{samples.name}", "--no_gt", "true",
           "--selective_evaluate", selected]
    env = dict(os.environ, PATH=os.environ.get("PATH", "") + ":" + ":".join(DOCKER_PATHS))
    with log.open("w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=4 * 3600)
    results_path = run_dir / f"{name}_eval_results.json"
    if proc.returncode != 0 or not results_path.exists():
        raise RuntimeError(f"BigCodeBench evaluator failed (exit {proc.returncode}); see {log}")
    ev = json.loads(results_path.read_text())["eval"]
    seen: Counter = Counter()
    out = []
    for local_id, code in items:
        tid = to_official(local_id)
        k = seen[tid]
        seen[tid] += 1
        res = ev[tid][k]
        if res["solution"].rstrip() and code.strip() and code.strip() not in res["solution"]:
            raise RuntimeError(f"Result order mismatch for {tid}#{k}")
        detail = res.get("details") or {}
        first = next(iter(detail.values()), "") if isinstance(detail, dict) else str(detail)
        out.append({"status": res["status"], "detail": str(first).strip().splitlines()[-1][:300] if first else ""})
    return out


def grade(items: Sequence[Tuple[str, str]], label: str, passes: int = 2) -> List[dict]:
    """Grade with `passes` independent evaluator runs; items whose runs disagree get
    one more run and the majority counts. Returns per item
    {"passed": bool, "statuses": [...], "flaky": bool, "detail": str}."""
    if not items:
        return []
    runs = [_grade_once(items, f"{label}_p{p + 1}") for p in range(passes)]
    out = []
    disagree = [i for i in range(len(items)) if len({r[i]["status"] for r in runs}) > 1]
    extra = {}
    if disagree:
        sub = [items[i] for i in disagree]
        for i, res in zip(disagree, _grade_once(sub, f"{label}_tiebreak")):
            extra[i] = res
    for i in range(len(items)):
        statuses = [r[i]["status"] for r in runs] + ([extra[i]["status"]] if i in extra else [])
        passed = sum(s == "pass" for s in statuses) * 2 > len(statuses)
        detail = next((r[i]["detail"] for r in runs if r[i]["detail"]), "")
        out.append({"passed": passed, "statuses": statuses, "flaky": i in extra, "detail": detail})
    return out


def grade_records(records: Iterable, label: str) -> Dict[str, int]:
    """Set record.passed (and grading notes) for records with a final artifact."""
    recs = [r for r in records if (r.final_artifact or "").strip()]
    results = grade([(r.task_id, r.final_artifact) for r in recs], label)
    counts = Counter()
    for r, res in zip(recs, results):
        r.passed = res["passed"]
        r.extra.pop("eval_error", None)
        r.extra["bcb_grade"] = {"statuses": res["statuses"], "flaky": res["flaky"],
                                "detail": res["detail"], "image": IMAGE}
        counts["scored"] += 1
        counts["flaky"] += int(res["flaky"])
    return dict(counts)
