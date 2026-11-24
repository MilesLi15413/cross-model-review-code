# Run:  PYTHONPATH=. .venv/bin/python scripts/bcb_self_preference.py
import csv
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.style_recognition_analysis import struct_sim, text_sim
from harness.core.parser import normalize_code_artifact

OUT = ROOT / "results/processed"
NAME = {"claude": "Claude", "gpt55": "GPT-5.5", "gemini": "Gemini"}
FAM = ("claude", "gpt55", "gemini")


def load():
    drafts = {}
    for row in csv.DictReader((OUT / "regression60_bcb_draft_inventory.csv").open()):
        rec = json.loads((ROOT / row["source_record_path"]).read_text())
        drafts[(row["writer"], row["problem_id"])] = (normalize_code_artifact(rec["writer_artifact"]).strip(), row["passed"] == "True")
    rows = []
    for f in glob.glob(str(ROOT / "results/raw/regression60_bcb_reviews/R_*/*.json")):
        r = json.loads(Path(f).read_text())
        e = r["extra"]
        rv, wr = e["reviewer_family"], e["writer_family"]
        code, before = drafts[(wr, r["task_id"])]
        rows.append({"reviewer": rv, "writer": wr, "problem": r["task_id"], "lines": int(e.get("diff_lines") or 0),
                     "unchanged": bool(e.get("unchanged_exact")), "before": before, "after": bool(r["passed"]), "draft": code})
    return drafts, rows


def write(name, rows):
    with (OUT / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    drafts, rows = load()
    own_rows, sim_rows = [], []
    for rv in FAM:
        own = [r for r in rows if r["reviewer"] == rv and r["writer"] == rv]
        oth = [r for r in rows if r["reviewer"] == rv and r["writer"] != rv]
        u = stats.mannwhitneyu([r["lines"] for r in own], [r["lines"] for r in oth])
        f_unch = stats.fisher_exact([[sum(r["unchanged"] for r in own), len(own) - sum(r["unchanged"] for r in own)],
                                     [sum(r["unchanged"] for r in oth), len(oth) - sum(r["unchanged"] for r in oth)]])[1]
        groups = [("own drafts", own)] + [(f"{NAME[w]}'s drafts", [r for r in oth if r["writer"] == w]) for w in FAM if w != rv] + [("other models' drafts", oth)]
        for grp, sub in groups:
            pas = [r for r in sub if r["before"]]
            fal = [r for r in sub if not r["before"]]
            own_rows.append({"reviewer": NAME[rv], "drafts": grp, "n": len(sub),
                             "unchanged": sum(r["unchanged"] for r in sub),
                             "unchanged_pct": round(100 * np.mean([r["unchanged"] for r in sub]), 1),
                             "mean_lines": round(float(np.mean([r["lines"] for r in sub])), 1),
                             "median_lines": float(np.median([r["lines"] for r in sub])),
                             "passing": len(pas), "broken": sum(not r["after"] for r in pas),
                             "failing": len(fal), "fixed": sum(r["after"] for r in fal),
                             "failing_left_unchanged": sum(r["unchanged"] for r in fal),
                             "p_lines_own_vs_other": u.pvalue, "p_unchanged_own_vs_other": f_unch})
        sims = []
        for r in oth:
            mine = drafts.get((rv, r["problem"]))
            if not mine:
                continue
            sims.append((text_sim(r["draft"], mine[0]), struct_sim(r["draft"], mine[0]), r["lines"], r["unchanged"]))
        for k, label in ((0, "text similarity"), (1, "structure similarity (names hidden)")):
            x = np.array([s[k] for s in sims])
            rho, p = stats.spearmanr(x, [s[2] for s in sims])
            unch = np.array([s[3] for s in sims])
            sim_rows.append({"reviewer": NAME[rv], "similarity": label, "n_other_drafts": len(sims),
                             "mean_similarity": round(float(x.mean()), 3), "spearman_vs_lines": round(float(rho), 3), "p": p,
                             "mean_sim_unchanged": round(float(x[unch].mean()), 3) if unch.any() else None,
                             "mean_sim_changed": round(float(x[~unch].mean()), 3)})
    write("bcb_self_preference_own_vs_other.csv", own_rows)
    write("bcb_self_preference_similarity.csv", sim_rows)
    for r in own_rows + sim_rows:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
