"""Free tests for the BigCodeBench follow-up (no Docker, no model calls)."""

from pathlib import Path

from experiments import run_bcb_writers as w
from harness.benchmarks import bigcodebench as bcb

ROOT = Path(__file__).resolve().parents[1]


def _task(tid, libs, prompt="Do X.\nYou should write self-contained code starting with:\n```\ndef task_func():\n```"):
    return {"task_id": tid, "libs": libs, "instruct_prompt": prompt}


def test_id_round_trip():
    assert bcb.to_local("BigCodeBench/16") == "bcb_16"
    assert bcb.to_official("bcb_16") == "BigCodeBench/16"


def test_eligible_drops_failing_reference_and_network_tasks():
    tasks = {
        "bcb_1": _task("BigCodeBench/1", ["pandas"]),
        "bcb_205": _task("BigCodeBench/205", ["subprocess"]),       # reference solution fails
        "bcb_3": _task("BigCodeBench/3", "['requests', 'json']"),    # network, string form
        "bcb_20": _task("BigCodeBench/20", ["numpy"]),
    }
    assert bcb.eligible(tasks) == ["bcb_1", "bcb_20"]


def test_render_fills_problem_and_drops_starter_code():
    out = bcb.render("P:\n{problem}\n{starter_code}\nEND", _task("BigCodeBench/1", []))
    assert "def task_func():" in out and "{starter_code}" not in out and "{problem}" not in out


def test_sample_is_seeded_and_prefix_consistent():
    pool = [f"bcb_{i}" for i in range(500)]
    a = w.sample_tasks(pool, 80)
    assert a == w.sample_tasks(pool, 80)
    assert w.sample_tasks(pool, 10) == a[:10]
    assert len(set(a)) == 80


def test_committed_task_list_matches_sampler():
    listed = (ROOT / "experiments/task_lists/bcb_80.txt").read_text().split()
    if bcb.TASKS_PATH.exists():
        assert listed == w.sample_tasks(bcb.eligible(bcb.load_tasks()))
    assert len(listed) == 80 and len(set(listed)) == 80


def test_prompts_differ_from_paper_only_in_domain_words():
    p = ROOT / "harness/prompts"
    lcb, new = (p / "writer_lcb.txt").read_text(), (p / "writer_bcb.txt").read_text()
    assert lcb.splitlines()[1:] == new.splitlines()[1:]
    lcb, new = (p / "reviewer_lcb.txt").read_text(), (p / "reviewer_bcb.txt").read_text()
    assert lcb.splitlines()[1:] == new.splitlines()[1:]


def test_grade_majority_vote(monkeypatch):
    calls = []

    def fake(items, label):
        calls.append(label)
        n = len(calls)
        # item 0 always passes; item 1 passes only on the first run, then the tie-break fails
        return [{"status": "pass", "detail": ""}, {"status": "pass" if n == 1 else "fail", "detail": "x"}][: len(items)] \
            if len(items) == 2 else [{"status": "fail", "detail": "x"}]

    monkeypatch.setattr(bcb, "_grade_once", fake)
    res = bcb.grade([("bcb_1", "a"), ("bcb_2", "b")], "t")
    assert [r["passed"] for r in res] == [True, False]
    assert res[1]["flaky"] and res[1]["statuses"] == ["pass", "fail", "fail"]
    assert len(calls) == 3
