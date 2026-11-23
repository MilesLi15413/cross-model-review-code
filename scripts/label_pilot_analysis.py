"""Pooled analysis of the authorship-label pilot (results/raw/label_pilot).

For each reviewer, pools its reviews across writers and compares label conditions on the
SAME draft (paired): unchanged (exact), changed lines, issues listed, outcome (pass).
Key contrasts:
  noise      : no label vs repeated no label (identical prompts) -> run-to-run noise floor
  self_pref  : false label naming the reviewer vs false label naming the third model
               (drafts the reviewer did not write; both labels equally wrong)
  true_none  : true label vs no label
  X_none     : each label condition vs no label
Tests: McNemar (exact) for binary, Wilcoxon signed-rank for counts; Holm within reviewer.
Output: results/processed/label_pilot_contrasts.csv
"""
import csv, glob, json, sys
from collections import defaultdict
from pathlib import Path
from scipy.stats import binomtest, wilcoxon

ROOT = Path(__file__).resolve().parents[1]
recs = defaultdict(dict)  # (reviewer, writer, task) -> {cond: metrics}
for f in glob.glob(str(ROOT / "results/raw/label_pilot/L_*/*.json")):
    r = json.loads(Path(f).read_text()); e = r["extra"]
    if r.get("passed") is None:
        continue
    arm = e["label_arm"]
    if arm == "false":
        cond = "false_self" if e["label_relation"] == "self" else "false_other"
    else:
        cond = arm  # true, none, none_repeat
    recs[(e["reviewer_family"], e["writer_family"], r["task_id"])][cond] = {
        "unchanged": bool(e.get("draft_unchanged")), "lines": int(e.get("diff_lines") or 0),
        "issues": int(e.get("issue_count") or 0), "passed": bool(r["passed"]),
        "draft_passed": bool(r["writer_passed"])}

def paired(rv, a, b, own=None):
    rows = [(v[a], v[b]) for (r, w, t), v in recs.items() if r == rv and a in v and b in v
            and (own is None or (w == r) == own)]
    out = {"reviewer": rv, "a": a, "b": b, "n": len(rows)}
    for m in ("unchanged", "passed"):
        x = sum(1 for p, q in rows if p[m] and not q[m]); y = sum(1 for p, q in rows if q[m] and not p[m])
        out[f"{m}_a"] = sum(p[m] for p, _ in rows); out[f"{m}_b"] = sum(q[m] for _, q in rows)
        out[f"{m}_disc"] = f"{x} vs {y}"; out[f"{m}_p"] = binomtest(x, x + y, .5).pvalue if x + y else 1.0
    for m in ("lines", "issues"):
        d = [p[m] - q[m] for p, q in rows]
        out[f"{m}_mean_a"] = round(sum(p[m] for p, _ in rows) / max(len(rows), 1), 1)
        out[f"{m}_mean_b"] = round(sum(q[m] for _, q in rows) / max(len(rows), 1), 1)
        out[f"{m}_p"] = wilcoxon(d).pvalue if any(d) else 1.0
    # outcome flips split by draft status
    out["breaks_a"] = sum(1 for p, _ in rows if p["draft_passed"] and not p["passed"])
    out["breaks_b"] = sum(1 for _, q in rows if q["draft_passed"] and not q["passed"])
    out["fixes_a"] = sum(1 for p, _ in rows if not p["draft_passed"] and p["passed"])
    out["fixes_b"] = sum(1 for _, q in rows if not q["draft_passed"] and q["passed"])
    return out

contrasts = [("none", "none_repeat", None, "noise"), ("false_self", "false_other", False, "self_pref"),
             ("true", "none", None, "true_none"), ("false_self", "none", False, "self_none"),
             ("false_other", "none", None, "other_none"), ("true", "none", True, "true_own_none")]
rows = []
for rv in ("claude", "gpt", "gemini"):
    block = []
    for a, b, own, name in contrasts:
        o = paired(rv, a, b, own); o["contrast"] = name; block.append(o)
    ps = sorted((o[k], i, k) for i, o in enumerate(block) for k in ("unchanged_p", "passed_p", "lines_p", "issues_p"))
    m = len(ps); run = 0
    for rank, (p, i, k) in enumerate(ps):
        run = max(run, min(1.0, p * (m - rank))); block[i][k.replace("_p", "_holm")] = round(run, 4)
    rows += block
for o in rows:
    for k in list(o):
        if k.endswith("_p"): o[k] = round(o[k], 4)
out = ROOT / "results/processed/label_pilot_contrasts.csv"
with out.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for o in rows:
    print(f"{o['reviewer']:<7}{o['contrast']:<14}n={o['n']:<3} unchanged {o['unchanged_a']}v{o['unchanged_b']} ({o['unchanged_disc']}, p={o['unchanged_p']}) "
          f"lines {o['lines_mean_a']}v{o['lines_mean_b']} (p={o['lines_p']}, holm={o['lines_holm']}) issues {o['issues_mean_a']}v{o['issues_mean_b']} (p={o['issues_p']}) "
          f"pass {o['passed_a']}v{o['passed_b']} ({o['passed_disc']}) breaks {o['breaks_a']}v{o['breaks_b']} fixes {o['fixes_a']}v{o['fixes_b']}")
