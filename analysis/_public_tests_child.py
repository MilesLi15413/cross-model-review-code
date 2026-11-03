"""Child entry point: run one draft on a task's public tests in a fresh interpreter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiment import get_adapter, merge_configs


def main() -> None:
    payload = json.loads(Path(sys.argv[1]).read_text())
    config = merge_configs(payload["config"], "livecodebench", payload["benchmark_config"])
    adapter = get_adapter("livecodebench", config)
    adapter.load_tasks([payload["task_id"]])
    problem = adapter._to_problem(payload["task_id"])

    from lcb_runner.evaluation.compute_code_generation_metrics import check_correctness

    tests = problem.public_test_cases
    sample = {
        "input_output": json.dumps(
            {
                "inputs": [test.input for test in tests],
                "outputs": [test.output for test in tests],
                "fn_name": problem.metadata.get("func_name", None),
            }
        )
    }
    results, _ = check_correctness(sample, payload["draft"], timeout=6, debug=False)
    passed = sum(1 for result in results if result is True or result == 1)
    Path(sys.argv[2]).write_text(json.dumps({"passed": passed, "total": len(tests)}))


if __name__ == "__main__":
    main()
