"""Batch Docker evaluation for SWE-bench prediction records."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


SWE_ROOT = Path(__file__).resolve().parents[3] / "external" / "swebench"

_METADATA_FILES = {"run_meta.json", "preflight.json", "index.json"}


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _check_prerequisites() -> None:
    if not SWE_ROOT.exists():
        raise FileNotFoundError(
            f"SWE-bench repo not found at {SWE_ROOT}. "
            "Run setup.sh or clone the benchmark into external/swebench."
        )


def _iter_condition_dirs(inputs_dir: str) -> List[Tuple[str, Path]]:
    root = Path(inputs_dir)
    if any(f for f in root.glob("*.json") if f.name not in _METADATA_FILES):
        return [(root.name, root)]

    condition_dirs = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and any(child.glob("*.json")):
            condition_dirs.append((child.name, child))
    return condition_dirs


def _load_records(condition_dir: Path) -> List[Dict[str, object]]:
    records = []
    for file_path in sorted(condition_dir.glob("*.json")):
        if file_path.name in _METADATA_FILES:
            continue
        records.append(json.loads(file_path.read_text()))
    return records


def _build_predictions(records: Iterable[Dict[str, object]], condition_id: str) -> List[Dict[str, object]]:
    predictions = []
    for record in records:
        if record.get("cli_error") or record.get("timed_out"):
            continue
        predictions.append(
            {
                "instance_id": record["task_id"],
                "model_name_or_path": condition_id,
                "model_patch": record.get("final_artifact", "") or "",
                "full_output": record.get("reviewer_stdout") or record.get("writer_stdout") or "",
            }
        )
    return predictions


def _parse_report(report_path: Path) -> Dict[str, bool]:
    payload = json.loads(report_path.read_text())
    results = {instance_id: False for instance_id in payload.get("submitted_ids", [])}
    for instance_id in payload.get("resolved_ids", []):
        results[instance_id] = True
    for instance_id in payload.get("unresolved_ids", []):
        results.setdefault(instance_id, False)
    for instance_id in payload.get("error_ids", []):
        results.setdefault(instance_id, False)
    return results


def _write_condition_outputs(
    output_condition_dir: Path,
    records: List[Dict[str, object]],
    pass_map: Dict[str, bool],
) -> None:
    output_condition_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        copied = dict(record)
        if record["task_id"] in pass_map:
            copied["passed"] = pass_map[record["task_id"]]
        target = output_condition_dir / f"{record['task_id']}__{record['condition']}.json"
        target.write_text(json.dumps(copied, indent=2))


def run_batch_eval(
    inputs_dir: str,
    output_dir: str,
    dataset_name: str,
    split: str,
    max_workers: int,
    timeout: int,
) -> None:
    _check_prerequisites()

    output_root = Path(output_dir).resolve()
    condition_dirs = _iter_condition_dirs(inputs_dir)
    if not condition_dirs:
        print(f"No condition result directories found under {inputs_dir}")
        return

    for condition_id, condition_dir in condition_dirs:
        records = _load_records(condition_dir)
        predictions = _build_predictions(records, condition_id)
        if not predictions:
            print(f"[{condition_id}] No predictions to evaluate.")
            continue

        output_condition_dir = output_root / condition_id
        output_condition_dir.mkdir(parents=True, exist_ok=True)
        predictions_path = (output_condition_dir / "predictions.jsonl").resolve()
        predictions_path.write_text(
            "\n".join(json.dumps(prediction) for prediction in predictions) + "\n"
        )

        run_id = f"{condition_id}-{_now_slug()}"
        cmd = [
            sys.executable,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            dataset_name,
            "--split",
            split,
            "--predictions_path",
            str(predictions_path),
            "--max_workers",
            str(max_workers),
            "--timeout",
            str(timeout),
            "--run_id",
            run_id,
        ]
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            cmd.extend(["--namespace", ""])

        print(f"[{condition_id}] Running: {' '.join(cmd)}")
        completed = subprocess.run(
            cmd,
            cwd=SWE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        (output_condition_dir / "stdout.log").write_text(completed.stdout)
        (output_condition_dir / "stderr.log").write_text(completed.stderr)
        if completed.returncode != 0:
            raise RuntimeError(
                f"SWE-bench evaluation failed for {condition_id}.\n"
                f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
            )

        report_name = f"{condition_id}.{run_id}.json"
        report_path = SWE_ROOT / report_name
        if not report_path.exists():
            report_path = SWE_ROOT / f"{condition_id.replace('/', '__')}.{run_id}.json"
        if not report_path.exists():
            raise FileNotFoundError(
                f"Expected SWE-bench report not found for {condition_id} and run_id {run_id}."
            )

        copied_report = output_condition_dir / "report.json"
        copied_report.write_text(report_path.read_text())
        pass_map = _parse_report(copied_report)
        _write_condition_outputs(output_condition_dir / "records", records, pass_map)
        print(
            f"[{condition_id}] Evaluation complete: "
            f"{sum(1 for passed in pass_map.values() if passed)}/{len(pass_map)} resolved"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, help="Root checkpoint dir or a single condition dir")
    parser.add_argument("--output", required=True, help="Output dir for evaluation artifacts")
    parser.add_argument(
        "--dataset-name",
        default="princeton-nlp/SWE-bench_Verified",
        help="SWE-bench dataset name or path",
    )
    parser.add_argument("--split", default="test")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    run_batch_eval(
        inputs_dir=args.inputs,
        output_dir=args.output,
        dataset_name=args.dataset_name,
        split=args.split,
        max_workers=args.max_workers,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
