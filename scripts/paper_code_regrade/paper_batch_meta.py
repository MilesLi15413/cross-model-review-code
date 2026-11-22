"""Paper-era batch grading, same as adapter.evaluate_batch, but keep LCB's per-problem metadata."""
import io, json, sys
from contextlib import redirect_stdout, redirect_stderr
sys.path.insert(0, ".")
def main():
    from experiments.run_experiment import get_adapter, merge_configs
    from harness.core.tracker import CostTracker
    from lcb_runner.evaluation import codegen_metrics
    src, out = sys.argv[1], sys.argv[2]; only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    cfg = merge_configs("experiments/configs/all_conditions.yaml", "livecodebench", "experiments/configs/livecodebench.yaml")
    ad = get_adapter("livecodebench", cfg)
    recs = [r for r in CostTracker().load_all(src) if not r.cli_error and not r.timed_out and (not only or r.task_id in only)]
    recs.sort(key=lambda r: r.task_id)
    ad.load_tasks([r.task_id for r in recs])
    samples = [ad._to_problem(r.task_id).get_evaluation_sample() for r in recs]
    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        m = codegen_metrics(samples, [[r.final_artifact or ""] for r in recs], k_list=[1],
                            num_process_evaluate=ad.num_process_evaluate, timeout=ad.timeout, debug=False)
    res = {r.task_id: {"tests": m[1][i][0], "meta": json.loads(m[2][i][0])} for i, r in enumerate(recs)}
    json.dump(res, open(out, "w"))
if __name__ == "__main__":
    main()
