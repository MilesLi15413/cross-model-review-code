# Run:  PYTHONPATH=. .venv/bin/python scripts/style_recognition_analysis.py
import csv
import difflib
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.run_style_recognition import clean_raw, load_drafts, structure_tokens

OUT = ROOT / "results/processed"
REC = ROOT / "results/raw/style_recognition"
FAM = {"claude": "claude", "gpt": "gpt55", "gpt55": "gpt55", "gemini": "gemini"}
NAME = {"claude": "Claude", "gpt55": "GPT-5.5", "gemini": "Gemini"}
ANS = {"Claude": "claude", "GPT": "gpt55", "Gemini": "gemini"}
REVIEWERS = ["claude", "gpt55", "gemini"]
RUNKEY = {"claude": "claude", "gpt55": "gpt", "gemini": "gemini"}


def holm(ps):
    order = np.argsort(ps)
    out, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, ps[i] * (len(ps) - rank)))
        out[i] = run
    return out


def clopper(k, n):
    if n == 0:
        return (float("nan"), float("nan"))
    lo = stats.beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
    return (lo, hi)


def write(name, rows):
    if not rows:
        return
    with (OUT / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def text_sim(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def struct_sim(a, b):
    return difflib.SequenceMatcher(None, structure_tokens(a), structure_tokens(b), autojunk=False).ratio()


def load_answers(condition="raw"):
    recs = [json.loads(Path(f).read_text()) for f in glob.glob(str(REC / condition / "*" / "*.json"))]
    for r in recs:
        r["reviewer_f"] = FAM[r["reviewer"]]
        r["answer_f"] = ANS.get(r["answer"]) if r.get("answer") else None
    return recs


def recognition_tables(condition):
    recs = [r for r in load_answers(condition) if r["rep"] == 1]
    if not recs:
        print(f"[{condition}] no style-recognition answers yet")
        return {}
    acc_rows, conf_rows, self_rows, pos_rows = [], [], [], []
    p_acc, p_self = [], []
    for rv in REVIEWERS:
        rs = [r for r in recs if r["reviewer_f"] == rv]
        valid = [r for r in rs if r["valid"]]
        k, n = sum(r["correct"] for r in valid), len(valid)
        p = stats.binomtest(k, n, 1 / 3, alternative="greater").pvalue if n else 1.0
        lo, hi = clopper(k, n)
        acc_rows.append({"condition": condition, "reviewer": NAME[rv], "calls": len(rs), "valid": n, "correct": k,
                         "accuracy": round(k / n, 3) if n else None, "ci_low": round(lo, 3), "ci_high": round(hi, 3), "p_vs_chance": p})
        p_acc.append(p)
        for tw in REVIEWERS:
            row = {"condition": condition, "reviewer": NAME[rv], "true_writer": NAME[tw]}
            sub = [r for r in valid if r["true_writer"] == tw]
            for aw in REVIEWERS:
                row[f"answered_{NAME[aw]}"] = sum(1 for r in sub if r["answer_f"] == aw)
            conf_rows.append(row)
        own = [r for r in valid if r["true_writer"] == rv]
        other = [r for r in valid if r["true_writer"] != rv]
        h, fa = sum(r["answered_self"] for r in own), sum(r["answered_self"] for r in other)
        table = [[h, len(own) - h], [fa, len(other) - fa]]
        pf = stats.fisher_exact(table, alternative="greater")[1] if own and other else 1.0
        self_rows.append({"condition": condition, "reviewer": NAME[rv], "own_drafts": len(own), "said_self_on_own": h,
                          "hit_rate": round(h / len(own), 3) if own else None, "other_drafts": len(other),
                          "said_self_on_other": fa, "false_alarm_rate": round(fa / len(other), 3) if other else None,
                          "p_fisher": pf})
        p_self.append(pf)
        pos = Counter(r["position_of_answer"] for r in valid)
        chi = stats.chisquare([pos.get(i, 0) for i in (1, 2, 3)]).pvalue if n else 1.0
        names = Counter(r["answer"] for r in valid)
        pos_rows.append({"condition": condition, "reviewer": NAME[rv], "pos1": pos.get(1, 0), "pos2": pos.get(2, 0),
                         "pos3": pos.get(3, 0), "p_uniform_position": chi, "answered_Claude": names.get("Claude", 0),
                         "answered_GPT": names.get("GPT", 0), "answered_Gemini": names.get("Gemini", 0)})
    for row, ph in zip(acc_rows, holm(p_acc)):
        row["p_holm"] = ph
    for row, ph in zip(self_rows, holm(p_self)):
        row["p_holm"] = ph
    write(f"style_recognition_accuracy_{condition}.csv", acc_rows)
    write(f"style_recognition_confusion_{condition}.csv", conf_rows)
    write(f"style_recognition_self_{condition}.csv", self_rows)
    write(f"style_recognition_position_{condition}.csv", pos_rows)
    for t in (acc_rows, self_rows, pos_rows):
        for r in t:
            print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    reps = defaultdict(dict)
    for r in load_answers(condition):
        reps[(r["reviewer_f"], r["true_writer"], r["problem"])][r["rep"]] = r.get("answer")
    pairs = [v for v in reps.values() if 1 in v and 2 in v]
    if pairs:
        same = sum(1 for v in pairs if v[1] == v[2])
        print(f"[{condition}] repeat stability: same answer in {same}/{len(pairs)} repeated calls")
        write(f"style_recognition_stability_{condition}.csv",
              [{"reviewer": NAME[rv], "repeated": sum(1 for (a, _, _), v in reps.items() if a == rv and 1 in v and 2 in v),
                "same_answer": sum(1 for (a, _, _), v in reps.items() if a == rv and 1 in v and 2 in v and v[1] == v[2])} for rv in REVIEWERS])
    return {(r["reviewer_f"], r["true_writer"], r["problem"]): r["answered_self"] for r in recs if r["valid"]}


def own_drafts():
    return {(d["writer"], d["problem"]): d["raw"] for d in load_drafts()}


def review_rows():
    own = own_drafts()
    rows = []
    for f in glob.glob(str(ROOT / "results/raw/regression60_reviews/R_*/*.json")):
        r = json.loads(Path(f).read_text())
        e = r["extra"]
        rows.append({"study": "regression60", "reviewer": FAM[e["reviewer_family"]], "writer": FAM[e["writer_family"]],
                     "problem": r["task_id"], "lines": int(e.get("diff_lines") or 0), "unchanged": bool(e.get("unchanged_exact")),
                     "draft": clean_raw(r["writer_artifact"])})
    for f in glob.glob(str(ROOT / "results/raw/label_pilot/L_*/*.json")):
        r = json.loads(Path(f).read_text())
        e = r["extra"]
        if e["label_arm"] not in ("none", "none_repeat"):
            continue
        rows.append({"study": "label_pilot_no_label", "reviewer": FAM[e["reviewer_family"]], "writer": FAM[e["writer_family"]],
                     "problem": r["task_id"], "lines": int(e.get("diff_lines") or 0), "unchanged": bool(e.get("draft_unchanged")),
                     "draft": clean_raw(r["writer_artifact"])})
    cache = {}
    for row in rows:
        mine = own[(row["reviewer"], row["problem"])]
        key = (row["reviewer"], row["writer"], row["problem"])
        if key not in cache:
            cache[key] = (text_sim(row["draft"], mine), struct_sim(row["draft"], mine))
        row["text_sim"], row["struct_sim"] = cache[key]
    return rows


def ols(X, y):
    X = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(len(y) - X.shape[1], 1)
    cov = np.linalg.pinv(X.T @ X) * (resid @ resid) / dof
    se = np.sqrt(np.diag(cov))
    p = 2 * stats.t.sf(np.abs(beta / se), dof)
    return beta[1:], se[1:], p[1:]


def logit(X, y, iters=50):
    X = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        W = p * (1 - p) + 1e-9
        H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(X.shape[1])
        b += np.linalg.solve(H, X.T @ (y - p))
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    pv = 2 * stats.norm.sf(np.abs(b / se))
    return b[1:], se[1:], pv[1:]


def agreement(believes):
    rows = review_rows()
    out, simtab = [], []
    for study in ("regression60", "label_pilot_no_label"):
        for rv in REVIEWERS:
            sub = [r for r in rows if r["study"] == study and r["reviewer"] == rv and r["writer"] != rv]
            if not sub:
                continue
            y_lines = np.log1p([r["lines"] for r in sub])
            y_unch = np.array([float(r["unchanged"]) for r in sub])
            for sim in ("text_sim", "struct_sim"):
                x = np.array([r[sim] for r in sub])
                rho, prho = stats.spearmanr(x, [r["lines"] for r in sub])
                rec = {"study": study, "reviewer": NAME[rv], "drafts": "other models' only", "n": len(sub), "similarity": sim,
                       "spearman_sim_vs_lines": round(rho, 3), "p_spearman": prho,
                       "mean_sim_unchanged": round(float(x[y_unch == 1].mean()), 3) if y_unch.sum() else None,
                       "mean_sim_changed": round(float(x[y_unch == 0].mean()), 3) if (y_unch == 0).sum() else None}
                bs = [believes.get((rv, r["writer"], r["problem"])) for r in sub]
                keep = [i for i, b in enumerate(bs) if b is not None]
                if keep and len({bs[i] for i in keep}) > 1:
                    X = np.column_stack([x[keep], [float(bs[i]) for i in keep]])
                    bl, sl, pl = ols(X, y_lines[keep])
                    rec.update({"n_with_answer": len(keep), "n_believed_self": int(sum(bs[i] for i in keep)),
                                "loglines_coef_sim": round(bl[0], 3), "p_sim": pl[0],
                                "loglines_coef_believes_self": round(bl[1], 3), "p_believes_self": pl[1]})
                    if 0 < y_unch[keep].sum() < len(keep):
                        bu, su, pu = logit(X, y_unch[keep])
                        rec.update({"unchanged_logodds_sim": round(bu[0], 3), "p_unch_sim": pu[0],
                                    "unchanged_logodds_believes_self": round(bu[1], 3), "p_unch_believes_self": pu[1]})
                elif keep:
                    rec.update({"n_with_answer": len(keep), "n_believed_self": int(sum(bs[i] for i in keep))})
                out.append(rec)
        for rv in REVIEWERS:
            for wr in REVIEWERS:
                sub = [r for r in rows if r["study"] == study and r["reviewer"] == rv and r["writer"] == wr]
                if sub:
                    simtab.append({"study": study, "reviewer": NAME[rv], "writer": NAME[wr], "n": len(sub),
                                   "mean_text_sim_to_reviewer_own": round(float(np.mean([r["text_sim"] for r in sub])), 3),
                                   "mean_struct_sim_to_reviewer_own": round(float(np.mean([r["struct_sim"] for r in sub])), 3),
                                   "mean_lines": round(float(np.mean([r["lines"] for r in sub])), 1),
                                   "unchanged": sum(r["unchanged"] for r in sub)})
    write("style_recognition_agreement.csv", out)
    write("style_recognition_similarity_by_pair.csv", simtab)
    for r in simtab:
        print(r)
    for r in out:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


def main():
    believes = recognition_tables("raw")
    recognition_tables("nocomments")
    agreement(believes)


if __name__ == "__main__":
    main()
