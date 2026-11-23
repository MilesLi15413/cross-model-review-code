# Run:  PYTHONPATH=. .venv/bin/python scripts/style_recognition_baseline.py
import collections
import csv
import io
import json
import math
import re
import sys
import tokenize
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.run_style_recognition import load_drafts, structure_tokens

WRITERS = ["claude", "gpt55", "gemini"]
OUT = ROOT / "results/processed"


def surface_features(code):
    lines = code.split("\n")
    n = max(len(lines), 1)
    nonblank = [l for l in lines if l.strip()]
    comment_lines = [l for l in lines if l.strip().startswith("#")]
    inline = 0
    try:
        for t in tokenize.generate_tokens(io.StringIO(code).readline):
            if t.type == tokenize.COMMENT and t.line.strip() and not t.line.strip().startswith("#"):
                inline += 1
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    names = re.findall(r"\b[a-z_][a-z0-9_]*\b", code)
    return {
        "lines": math.log1p(len(lines)),
        "comment_line_frac": len(comment_lines) / n,
        "inline_comments": math.log1p(inline),
        "blank_frac": sum(1 for l in lines if not l.strip()) / n,
        "ws_only_lines": sum(1 for l in lines if l and not l.strip()) / n,
        "mean_len": float(np.mean([len(l) for l in nonblank])) / 80 if nonblank else 0,
        "max_len": max((len(l) for l in lines), default=0) / 120,
        "docstring": float('"""' in code or "'''" in code),
        "type_hints": math.log1p(len(re.findall(r"->|:\s*(?:int|str|List|Dict|list|dict|float|bool)\b", code))),
        "sys_stdin": float("sys.stdin" in code),
        "input_call": float("input()" in code),
        "def_main": float("def main" in code),
        "name_main": float("__name__" in code),
        "fstring": math.log1p(len(re.findall(r"\bf[\"']", code))),
        "lambda": math.log1p(code.count("lambda")),
        "comprehension": math.log1p(len(re.findall(r"\[[^\]]*\bfor\b", code))),
        "mean_name_len": float(np.mean([len(x) for x in names])) / 10 if names else 0,
        "underscore_names": sum(1 for x in names if "_" in x.strip("_")) / max(len(names), 1),
        "single_letter": sum(1 for x in names if len(x) == 1) / max(len(names), 1),
        "functions": math.log1p(len(re.findall(r"^\s*def ", code, re.M))),
        "nonlocal_global": math.log1p(len(re.findall(r"\b(?:nonlocal|global)\b", code))),
        "setrecursionlimit": float("setrecursionlimit" in code),
    }


def softmax_fit(X, y, k, l2=1.0, iters=3000, lr=0.5):
    W = np.zeros((X.shape[1], k))
    Y = np.eye(k)[y]
    for _ in range(iters):
        Z = X @ W
        Z -= Z.max(1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(1, keepdims=True)
        W -= lr * (X.T @ (P - Y) / len(X) + l2 * W / len(X))
    return W


def nb_fit(docs, y, k, alpha=1.0):
    vocab = {}
    for d in docs:
        for t in d:
            vocab.setdefault(t, len(vocab))
    C = np.full((k, len(vocab)), alpha)
    for d, c in zip(docs, y):
        for t in d:
            C[c, vocab[t]] += 1
    logp = np.log(C / C.sum(1, keepdims=True))
    return vocab, logp


def nb_predict(model, doc):
    vocab, logp = model
    idx = [vocab[t] for t in doc if t in vocab]
    return int(np.argmax(logp[:, idx].sum(1))) if idx else 0


def bigrams(tokens):
    return tokens + [a + " " + b for a, b in zip(tokens, tokens[1:])]


def text_tokens(code):
    return re.findall(r"[A-Za-z_]+|\S", code) + ["<ws_line>"] * sum(1 for l in code.split("\n") if l and not l.strip())


def loo_problem(drafts, predict_fn):
    problems = sorted({d["problem"] for d in drafts})
    conf = np.zeros((3, 3), int)
    for p in problems:
        train = [d for d in drafts if d["problem"] != p]
        test = [d for d in drafts if d["problem"] == p]
        for d, pred in zip(test, predict_fn(train, test)):
            conf[WRITERS.index(d["writer"]), pred] += 1
    return conf


def run_features(cond):
    def fn(train, test):
        keys = list(surface_features("x=1").keys())
        Xtr = np.array([[surface_features(d[cond])[k] for k in keys] for d in train])
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        Xtr = np.hstack([(Xtr - mu) / sd, np.ones((len(train), 1))])
        W = softmax_fit(Xtr, np.array([WRITERS.index(d["writer"]) for d in train]), 3)
        Xte = np.array([[surface_features(d[cond])[k] for k in keys] for d in test])
        Xte = np.hstack([(Xte - mu) / sd, np.ones((len(test), 1))])
        return list(np.argmax(Xte @ W, 1))
    return fn


def run_nb(cond, tok):
    def fn(train, test):
        m = nb_fit([bigrams(tok(d[cond])) for d in train], [WRITERS.index(d["writer"]) for d in train], 3)
        return [nb_predict(m, bigrams(tok(d[cond]))) for d in test]
    return fn


def main():
    drafts = load_drafts()
    rows = []
    models = {
        "surface features (logistic)": run_features,
        "text tokens (naive Bayes)": lambda c: run_nb(c, text_tokens),
        "code structure only (naive Bayes)": lambda c: run_nb(c, structure_tokens),
    }
    for cond in ("raw", "nocomments"):
        for name, mk in models.items():
            conf = loo_problem(drafts, mk(cond))
            acc = np.trace(conf) / conf.sum()
            per = {w: conf[i, i] / conf[i].sum() for i, w in enumerate(WRITERS)}
            rows.append({"condition": cond, "classifier": name, "accuracy": round(acc, 3),
                         **{f"recall_{w}": round(v, 3) for w, v in per.items()},
                         "confusion_rows_true_cols_pred_claude_gpt55_gemini": json.dumps(conf.tolist())})
            print(f"{cond:<10} {name:<36} acc {acc:.3f}  " + "  ".join(f"{w} {v:.2f}" for w, v in per.items()) + f"  {conf.tolist()}")
    feats = collections.defaultdict(list)
    for d in drafts:
        for k, v in surface_features(d["raw"]).items():
            feats[(d["writer"], k)].append(v)
    keys = list(surface_features("x=1").keys())
    with (OUT / "style_recognition_baseline.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (OUT / "style_recognition_surface_features.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["feature"] + WRITERS)
        for k in keys:
            w.writerow([k] + [round(float(np.mean(feats[(wr, k)])), 3) for wr in WRITERS])
    print("\nMean raw-condition features by writer:")
    for k in keys:
        print(f"  {k:<20} " + "  ".join(f"{wr} {np.mean(feats[(wr, k)]):.3f}" for wr in WRITERS))


if __name__ == "__main__":
    main()
