# Run: PYTHON_BIN=.venv/bin/python; $PYTHON_BIN experiments/run_help_check.py  (rerun skips finished models)
"""Positive control for help-request tracking: one problem with its key rule left out."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from harness.core.cli_runner import CLIRunner, UsageLimitError
from harness.core.parser import parse_help_requests, parse_model_response
from harness.core.tracker import CostTracker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiments/configs/help_request_conditions.yaml")
    parser.add_argument("--problem", default="experiments/configs/help_check_problem.txt")
    parser.add_argument("--output", default="results/raw/demo_help_check")
    parser.add_argument("--summary", default="results/processed/help_check_demo.csv")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    template = Path("harness/prompts/writer_lcb_help.txt").read_text()
    prompt = template.replace("{problem}", Path(args.problem).read_text().strip()).replace("{starter_code}", "")
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    tracker = CostTracker(config.get("pricing_path", "experiments/configs/pricing.yaml"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for condition in config["conditions"]:
        writer = condition["writer"]
        path = out_dir / f"{condition['id']}.json"
        if not path.exists():
            runner = CLIRunner(
                writer["cli"], writer["model"], effort=writer.get("effort"),
                timeout_s=writer.get("timeout_s", 300), stop_on_limit=True,
            )
            try:
                result = runner.run(prompt, task_id="help_check", condition_id=condition["id"], turn="writer")
            except UsageLimitError as exc:
                print(exc)
                return 1
            parsed = parse_model_response(result.response_text)
            cost = result.cost_usd or tracker.compute_cost(
                writer["model"], result.input_tokens, result.output_tokens,
                cached_input_tokens=result.cached_input_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
            )
            record = {
                "condition": condition["id"],
                "cli": writer["cli"],
                "model": writer["model"],
                "effort": writer.get("effort"),
                "cli_version": runner.get_version(),
                "prompt_sha256": prompt_sha,
                "prompt": prompt,
                "cost_usd": cost,
                "result": asdict(result),
                "parse_method": parsed.parse_method,
                "help_tracking": parse_help_requests(result.response_text, parsed),
            }
            path.write_text(json.dumps(record, indent=2))
            print(f"{condition['id']}: ${cost:.3f} {result.duration_s:.0f}s", flush=True)

        record = json.loads(path.read_text())
        tracking = record["help_tracking"]
        rows.append(
            {
                "model": record["model"],
                "tagged_requests": tracking["tagged_count"],
                "types": ";".join(r["type"] for r in tracking["tagged_requests"]),
                "untagged_requests": tracking["untagged_count"],
                "malformed_tags": tracking["malformed_tags"],
                "no_code": tracking["no_code"],
                "cost_usd": round(record["cost_usd"], 4),
            }
        )

    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    with open(args.summary, "w", newline="") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer_csv.writeheader()
        writer_csv.writerows(rows)
    print(f"Saved {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
