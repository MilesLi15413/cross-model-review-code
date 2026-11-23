# Run:  PYTHONPATH=. .venv/bin/python experiments/run_style_recognition.py --limit-per-reviewer 5
#       PYTHONPATH=. .venv/bin/python experiments/run_style_recognition.py --conditions raw --max-spend gemini=11 --max-spend gpt=12
#       add --repeat N to ask the raw condition a second time for N seeded problems; --dry-run lists the calls
import argparse
import csv
import hashlib
import io
import json
import random
import re
import sys
import threading
import tokenize
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.core.cli_runner import CLIRunner, OutOfCreditsError, UsageLimitError
from harness.core.parser import normalize_code_artifact

SEED = 2026
OPTIONS = ["Claude", "GPT", "Gemini"]
FAMILY_NAME = {"claude": "Claude", "gpt55": "GPT", "gemini": "Gemini"}
REVIEWERS = {
    "claude": {"cli": "claude", "model": "claude-opus-4-7", "effort": "high", "codex_home": None},
    "gpt": {"cli": "codex", "model": "gpt-5.5", "effort": "high", "codex_home": "/Users/milesli/.codex-regression60"},
    "gemini": {"cli": "gemini", "model": "gemini-3.1-pro-preview", "effort": "high", "codex_home": None},
}
REVIEWER_NAME = {"claude": "Claude", "gpt": "GPT", "gemini": "Gemini"}
TEMPLATE_PATH = ROOT / "harness/prompts/style_recognition.txt"
INVENTORY = ROOT / "results/processed/regression60_draft_inventory.csv"
OUT = ROOT / "results/raw/style_recognition"
FROZEN = ["results/raw/lcb_hard_full", "results/raw/lcb_medium_100", "results/raw/regression60", "results/raw/label_pilot"]
SPEND_MARGIN_USD = 0.5
MAX_ATTEMPTS = 2


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_raw(artifact):
    text = normalize_code_artifact(artifact).strip()
    m = re.match(r"^```[A-Za-z0-9_+-]*[ \t]*\n(.*?)\n[ \t]*```", text, re.S)
    return (m.group(1) if m else text).strip()


def _docstring_lines(code):
    import ast
    lines = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def strip_comments(code):
    lines = code.split("\n")
    cut = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                cut[row] = min(cut.get(row, col), col)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code
    doc = _docstring_lines(code)
    out = []
    for i, line in enumerate(lines, start=1):
        if i in doc:
            continue
        if i in cut:
            new = line[: cut[i]].rstrip()
            if new.strip() == "":
                continue
            out.append(new)
        else:
            out.append(line)
    return "\n".join(out).strip()


def structure_tokens(code):
    import keyword
    import builtins
    keep = set(keyword.kwlist) | set(dir(builtins))
    toks = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.NAME:
                toks.append(tok.string if tok.string in keep else "ID")
            elif tok.type == tokenize.STRING:
                toks.append("STR")
            elif tok.type == tokenize.NUMBER:
                toks.append("NUM")
            else:
                toks.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code.split()
    return toks


def load_drafts():
    drafts = []
    for row in csv.DictReader(INVENTORY.open()):
        rec = json.loads((ROOT / row["source_record_path"]).read_text())
        raw = clean_raw(rec.get("final_artifact") or rec.get("writer_artifact") or "")
        drafts.append({"problem": row["problem_id"], "writer": row["writer"], "passed": row["passed"] == "True",
                       "source": row["source_record_path"], "raw": raw, "nocomments": strip_comments(raw)})
    return drafts


def option_order(reviewer, draft, condition, rep):
    opts = list(OPTIONS)
    random.Random(f"{SEED}|{reviewer}|{draft['writer']}|{draft['problem']}|{condition}|{rep}").shuffle(opts)
    return opts


def build_prompt(template, options, code):
    return (template.replace("{option_1}", options[0]).replace("{option_2}", options[1])
            .replace("{option_3}", options[2]).replace("{code}", code))


def parse_answer(text):
    t = (text or "").strip()
    t = re.sub(r"^[\s\"'`*_]+|[\s\"'`*_.]+$", "", t)
    for name in OPTIONS:
        if t.lower() == name.lower():
            return name
    return None


def repeat_problems(n):
    problems = sorted({d["problem"] for d in load_drafts()})
    random.Random(f"{SEED}|repeat").shuffle(problems)
    return set(problems[:n])


def build_cells(drafts, conditions, reviewers, repeat_set):
    cells = []
    for reviewer in reviewers:
        for d in drafts:
            for condition in conditions:
                cells.append({"reviewer": reviewer, "draft": d, "condition": condition, "rep": 1})
                if condition == "raw" and d["problem"] in repeat_set:
                    cells.append({"reviewer": reviewer, "draft": d, "condition": condition, "rep": 2})
    random.Random(f"{SEED}|cells").shuffle(cells)
    return cells


def cell_path(cell):
    d = cell["draft"]
    suffix = "" if cell["rep"] == 1 else f"__rep{cell['rep']}"
    return OUT / cell["condition"] / cell["reviewer"] / f"{d['writer']}__{d['problem']}{suffix}.json"


def reviewer_spend():
    spend = {k: 0.0 for k in REVIEWERS}
    for f in OUT.glob("*/*/*.json"):
        r = json.loads(f.read_text())
        spend[r["reviewer"]] += r.get("cost_usd_all_attempts", 0.0)
    return spend


def run_cell(cell, template, stop_on_limit):
    d, reviewer, condition = cell["draft"], cell["reviewer"], cell["condition"]
    cfg = REVIEWERS[reviewer]
    options = option_order(reviewer, d, condition, cell["rep"])
    code = d[condition]
    prompt = build_prompt(template, options, code)
    runner = CLIRunner(cli=cfg["cli"], model=cfg["model"], effort=cfg["effort"], timeout_s=1800,
                       paused_sentinel_path=str(OUT / "PAUSED"), stop_on_limit=stop_on_limit, codex_home=cfg["codex_home"])
    rec = {"problem": d["problem"], "true_writer": d["writer"], "true_writer_name": FAMILY_NAME[d["writer"]],
           "draft_passed": d["passed"], "source_record": d["source"], "reviewer": reviewer, "condition": condition,
           "rep": cell["rep"], "options": options, "code_sha256": sha256(code), "prompt_sha256": sha256(prompt),
           "template_sha256": sha256(template), "attempts": [], "cost_usd_all_attempts": 0.0}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            res = runner.run(prompt, task_id=d["problem"], condition_id=f"style_{condition}", turn="reviewer")
        except UsageLimitError:
            raise
        except Exception as exc:
            rec["attempts"].append({"error": str(exc)[:500]})
            continue
        parsed = parse_answer(res.response_text)
        settings = res.runtime_settings or {}
        rec["attempts"].append({"raw_answer": res.response_text[:2000], "parsed": parsed, "cost_usd": res.cost_usd or 0.0,
                                "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                                "cached_input_tokens": res.cached_input_tokens,
                                "cache_creation_input_tokens": res.cache_creation_input_tokens,
                                "latency_s": res.duration_s, "cli_version": res.cli_version,
                                "tool_calls": settings.get("tool_calls"), "runtime_settings": settings})
        rec["cost_usd_all_attempts"] += res.cost_usd or 0.0
        if parsed:
            break
    last = rec["attempts"][-1] if rec["attempts"] else {}
    rec["raw_answer"] = last.get("raw_answer")
    rec["answer"] = last.get("parsed")
    rec["valid"] = rec["answer"] is not None
    rec["answered_self"] = rec["valid"] and rec["answer"] == REVIEWER_NAME[reviewer]
    rec["correct"] = rec["valid"] and rec["answer"] == FAMILY_NAME[d["writer"]]
    rec["position_of_answer"] = options.index(rec["answer"]) + 1 if rec["valid"] else None
    path = cell_path(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="raw", help="comma list of raw,nocomments")
    ap.add_argument("--reviewers", default="claude,gpt,gemini")
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--limit-per-reviewer", type=int, default=0)
    ap.add_argument("--max-spend", action="append", default=[], metavar="REVIEWER=USD")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--stop-on-limit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    assert all(not str(OUT).startswith(str(ROOT / f)) for f in FROZEN)
    caps = {k: float(v) for k, v in (s.split("=", 1) for s in args.max_spend)}
    template = TEMPLATE_PATH.read_text()
    drafts = load_drafts()
    cells = build_cells(drafts, args.conditions.split(","), args.reviewers.split(","), repeat_problems(args.repeat) if args.repeat else set())
    pending = [c for c in cells if not cell_path(c).exists()]
    if args.limit_per_reviewer:
        done = {r: sum(1 for c in cells if c["reviewer"] == r and cell_path(c).exists()) for r in REVIEWERS}
        picked, count = [], dict(done)
        for c in pending:
            if count[c["reviewer"]] < args.limit_per_reviewer:
                picked.append(c)
                count[c["reviewer"]] += 1
        pending = picked
    print(f"{len(cells)} cells planned, {len(cells) - len([c for c in cells if not cell_path(c).exists()])} done, {len(pending)} to run now.")
    if args.dry_run:
        for c in pending[:20]:
            print(" ", c["reviewer"], c["condition"], c["rep"], c["draft"]["writer"], c["draft"]["problem"])
        return
    spend = reviewer_spend()
    print(f"Recorded spend: { {k: round(v, 3) for k, v in spend.items()} }; caps: {caps}")
    lock, stop, capped = threading.Lock(), threading.Event(), set()
    limit_error = None

    def work(c):
        if stop.is_set():
            return None
        with lock:
            if c["reviewer"] in caps and spend[c["reviewer"]] + SPEND_MARGIN_USD >= caps[c["reviewer"]]:
                capped.add(c["reviewer"])
                return None
        rec = run_cell(c, template, args.stop_on_limit)
        with lock:
            spend[c["reviewer"]] += rec["cost_usd_all_attempts"]
        return rec

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(work, c): c for c in pending}
        for i, fut in enumerate(as_completed(futs), start=1):
            try:
                rec = fut.result()
            except UsageLimitError as exc:
                stop.set()
                limit_error = exc
                continue
            if rec:
                print(f"  [{i}/{len(pending)}] {rec['reviewer']} {rec['condition']} {rec['true_writer']} {rec['problem']} "
                      f"-> {rec['answer']} ({'ok' if rec['correct'] else 'x'}) ${rec['cost_usd_all_attempts']:.4f}", flush=True)
    print(f"Recorded spend: { {k: round(v, 3) for k, v in spend.items()} }")
    if capped:
        raise SystemExit(f"Spending cap reached for {sorted(capped)}; finished cells are saved.")
    if isinstance(limit_error, OutOfCreditsError):
        raise SystemExit(f"HARD STOP: {limit_error}\nFinished cells are saved.")
    if limit_error:
        raise SystemExit(f"{limit_error}\nFinished cells are saved; rerun the same command to continue.")


if __name__ == "__main__":
    main()
