"""Item 3 (free): classify every break (passing draft -> failing review) and test whether
edit size predicts breaking.

LiveCodeBench: each broken program is re-run with the paper's grader in a fresh
interpreter (see analysis/_lcb_eval_child.py for why) and the first failing test's
error code is read: -2 wrong answer, -3 too slow, -4 crash, -1 whole-run timeout.
BigCodeBench: the stored evaluator detail is used (timeout status = too slow; an
exception other than AssertionError = crash; otherwise wrong answer).
Edit size: diff_lines of every review of a passing draft, breaks vs non-breaks
(one-sided Mann-Whitney U per reviewer).

Outputs: results/processed/regression60_break_types.csv, regression60_edit_size.csv
"""
import csv, glob, json, os, re, signal, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SETS = {  # label -> (checkpoint, condition suffix, benchmark)
    "lcb_stage2": ("results/raw/regression60_reviews", "", "lcb"),
    "lcb_rep2": ("results/raw/regression60_gpt_rep2", "__rep2", "lcb"),
    "lcb_minedit": ("results/raw/regression60_gpt_minedit", "__minedit", "lcb"),
    "bcb": ("results/raw/regression60_bcb_reviews", "", "bcb"),
}
WALL_S = 600  # per program; the grader's per-test limit is not enforced for some hung programs
CODES = {-1: "too slow (whole run)", -2: "wrong answer", -3: "too slow", -4: "crash"}


def child() -> None:
    """Run in a fresh interpreter: grade items and print first-failure metadata as JSON."""
    from experiments.run_experiment import get_adapter, merge_configs
    from harness.benchmarks.livecodebench.adapter import _load_lcb_runner
    from harness.core.parser import normalize_code_artifact
    items = json.loads(Path(sys.argv[2]).read_text())
    cfg = merge_configs("experiments/configs/all_conditions.yaml", "livecodebench",
                        "experiments/configs/livecodebench.yaml")
    ad = get_adapter("livecodebench", cfg)
    ad.load_tasks(sorted({i["task_id"] for i in items}))
    _, codegen_metrics, _ = _load_lcb_runner()
    out = []
    for it in items:
        sample = ad._to_problem(it["task_id"]).get_evaluation_sample()
        m = codegen_metrics([sample], [[normalize_code_artifact(it["code"])]], k_list=[1],
                            num_process_evaluate=1, timeout=ad.timeout, debug=False)
        res, meta = m[1][0][0], json.loads(m[2][0][0])
        out.append({"key": it["key"], "results_tail": [r for r in res if r is not True][:1],
                    "error_code": meta.get("error_code"), "error_message": meta.get("error_message", ""),
                    "error": str(meta.get("error", ""))[:200]})
    Path(sys.argv[3]).write_text(json.dumps(out))


def load(cp: str, suffix: str) -> list[dict]:
    recs = []
    for f in sorted(glob.glob(f"{ROOT}/{cp}/R_*/*.json")):
        r = json.loads(Path(f).read_text())
        m = re.match(r"R_(\w+?)_by_(\w+?)" + re.escape(suffix) + r"$", r["condition"])
        if not m or r.get("passed") is None or r.get("writer_passed") is None:
            continue
        recs.append({"rec": r, "writer": m.group(1), "reviewer": m.group(2), "path": f})
    return recs


def bcb_type(r: dict) -> str:
    g = r["extra"].get("bcb_grade", {})
    if "timeout" in g.get("statuses", []):
        return "too slow"
    d = g.get("detail", "")
    m = re.match(r"^(\w+(Error|Exception))\b", d)
    return "crash" if m and m.group(1) != "AssertionError" else "wrong answer"


def main() -> None:
    from scipy.stats import mannwhitneyu
    import numpy as np
    breaks, edits = [], []
    for label, (cp, suffix, bench) in SETS.items():
        for x in load(cp, suffix):
            r = x["rec"]
            if r["writer_passed"] is not True:
                continue
            broke = r["passed"] is False
            edits.append({"set": label, "reviewer": x["reviewer"], "writer": x["writer"],
                          "problem_id": r["task_id"], "diff_lines": r["extra"].get("diff_lines", 0), "broke": broke})
            if broke:
                breaks.append({"set": label, "problem_id": r["task_id"], "writer": x["writer"],
                               "reviewer": x["reviewer"], "diff_lines": r["extra"].get("diff_lines", 0),
                               "type": bcb_type(r) if bench == "bcb" else None,
                               "detail": r["extra"].get("bcb_grade", {}).get("detail", "")[:150] if bench == "bcb" else "",
                               "code": r["final_artifact"]})
    lcb = [b for b in breaks if b["type"] is None]
    for i, b in enumerate(lcb):  # one fresh interpreter per program, capped at 10 min
        with tempfile.TemporaryDirectory() as td:
            inp, outp = Path(td) / "in.json", Path(td) / "out.json"
            inp.write_text(json.dumps([{"key": 0, "task_id": b["problem_id"], "code": b["code"]}]))
            proc = subprocess.Popen([sys.executable, __file__, "--child", str(inp), str(outp)], cwd=ROOT,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                proc.wait(timeout=WALL_S)
                o = json.loads(outp.read_text())[0]
                b["type"] = CODES.get(o["error_code"], f"other ({o['error_code']})")
                b["detail"] = (o["error_message"] + " " + o["error"]).strip()[:150]
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                b["type"], b["detail"] = "too slow", f"did not finish the hidden tests in {WALL_S}s"
        print(f"  [{i+1}/{len(lcb)}] {b['set']} {b['problem_id']} {b['writer']}->{b['reviewer']}: {b['type']}", flush=True)
    fields = ["set", "problem_id", "writer", "reviewer", "diff_lines", "type", "detail"]
    with (ROOT / "results/processed/regression60_break_types.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(breaks)
    with (ROOT / "results/processed/regression60_edit_size.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(edits[0])); w.writeheader(); w.writerows(edits)

    print("\nBreak types:")
    for s in SETS:
        bs = [b for b in breaks if b["set"] == s]
        counts = {}
        for b in bs:
            counts[(b["reviewer"], b["type"])] = counts.get((b["reviewer"], b["type"]), 0) + 1
        print(f"  {s}: {len(bs)} breaks", dict(sorted(counts.items())))
    print("\nEdit size (diff lines) on passing drafts, breaks vs not (Mann-Whitney):")
    for s in SETS:
        for rv in ("claude", "gemini", "gpt55"):
            e = [x for x in edits if x["set"] == s and x["reviewer"] == rv]
            b = [x["diff_lines"] for x in e if x["broke"]]; nb = [x["diff_lines"] for x in e if not x["broke"]]
            if b and nb:
                p = mannwhitneyu(b, nb, alternative="greater").pvalue
                print(f"  {s:<12}{rv:<7} breaks n={len(b):>2} median {np.median(b):>5.1f} | "
                      f"others n={len(nb):>3} median {np.median(nb):>5.1f} | p={p:.4f}")


if __name__ == "__main__":
    child() if sys.argv[1:2] == ["--child"] else main()
