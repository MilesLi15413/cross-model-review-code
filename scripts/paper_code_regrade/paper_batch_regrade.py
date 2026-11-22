"""Regrade frozen records with the PAPER-ERA code (commit 6581226), mirroring
run_experiment._run_condition_batch_eval: adapter.evaluate_batch(all records of a
condition), in-process, paper configs. Frozen records are only read."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from experiments.run_experiment import get_adapter, merge_configs
from harness.core.tracker import CostTracker
def main():
    src, label = sys.argv[1], sys.argv[2]
    cfg = merge_configs("experiments/configs/all_conditions.yaml", "livecodebench", "experiments/configs/livecodebench.yaml")
    ad = get_adapter("livecodebench", cfg)
    print("adapter timeout", ad.timeout, "workers", ad.num_process_evaluate, flush=True)
    recs = CostTracker().load_all(src)
    ad.load_tasks(sorted({r.task_id for r in recs}))
    paper = {r.task_id: r.passed for r in recs}
    t0 = time.time(); res = ad.evaluate_batch(recs)
    print(f"{label}: {len(res)} scored in {time.time()-t0:.0f}s", flush=True)
    json.dump({"paper": paper, "regrade": res}, open(f"{label}.json", "w"))
    pp = sum(bool(v) for v in paper.values()); rp = sum(bool(res.get(k)) for k in paper)
    ft = sorted(k for k in paper if not paper[k] and res.get(k)); tf = sorted(k for k in paper if paper[k] and res.get(k) is False)
    print(f"paper {pp}/{len(paper)}  paper-code regrade {rp}/{len(paper)}  fail->pass {ft}  pass->fail {tf}")


if __name__ == "__main__":
    main()
