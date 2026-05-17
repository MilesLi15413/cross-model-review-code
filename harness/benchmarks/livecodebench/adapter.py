"""LiveCodeBench adapter built around the upstream custom-evaluator format."""

from __future__ import annotations

import json
import io
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from lcb_runner.benchmarks.code_generation import CodeGenerationProblem
from lcb_runner.evaluation import codegen_metrics, extract_instance_results

from harness.benchmarks.livecodebench.dataset_loader import (
    iter_hf_lcb_rows_stream,
    iter_hf_lcb_rows_with_files,
    load_lcb_rows,
)
from harness.core.pipeline import BenchmarkTask
from harness.core.tracker import TaskRecord


LCB_ROOT = Path(__file__).resolve().parents[3] / "external" / "livecodebench"


def _load_prompts() -> tuple[str, str]:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    return (
        (prompts_dir / "writer_lcb.txt").read_text(),
        (prompts_dir / "reviewer_lcb.txt").read_text(),
    )


@dataclass
class LCBTask:
    task_id: str
    problem_statement: str
    difficulty: str
    starter_code: str
    raw: Dict[str, object]


class LiveCodeBenchAdapter:
    """Loads tasks and evaluates selected records in-process with LCB metrics."""

    def __init__(
        self,
        dataset_path: Optional[str] = None,
        release_version: str = "release_latest",
        scenario: str = "codegeneration",
        num_process_evaluate: int = 4,
        timeout: int = 10,
    ):
        self.dataset_path = Path(dataset_path) if dataset_path else None
        self.release_version = release_version
        self.scenario = scenario
        self.num_process_evaluate = num_process_evaluate
        self.timeout = timeout
        self.writer_template, self.reviewer_template = _load_prompts()
        self._cache: Dict[str, LCBTask] = {}
        self._all_task_ids: Optional[List[str]] = None
        self._hf_logged_shards: set[str] = set()
        self._check_prerequisites()

    def _check_prerequisites(self) -> None:
        if not LCB_ROOT.exists():
            raise FileNotFoundError(
                f"LiveCodeBench repo not found at {LCB_ROOT}. "
                "Run setup.sh or clone the benchmark into external/livecodebench."
            )

    def _task_path(self, task_id: str) -> Path:
        if self.dataset_path is None:
            raise FileNotFoundError("No local LiveCodeBench dataset path configured.")
        direct = self.dataset_path / f"{task_id}.json"
        if direct.exists():
            return direct
        for candidate in self.dataset_path.rglob(f"{task_id}.json"):
            return candidate
        raise FileNotFoundError(f"LiveCodeBench task {task_id} not found under {self.dataset_path}")

    def _cache_hf_task_row(self, row: Dict[str, object]) -> None:
        task_id = str(row["question_id"])
        self._cache[task_id] = LCBTask(
            task_id=task_id,
            problem_statement=str(row.get("question_content", "")),
            difficulty=str(row.get("difficulty", "medium")),
            starter_code=str(row.get("starter_code", "")),
            raw=dict(row),
        )

    def _load_hf_task_cache(self, target_ids: Optional[set[str]] = None) -> None:
        if target_ids is not None and target_ids.issubset(self._cache.keys()):
            return
        if target_ids is None and self._cache:
            return

        if target_ids is None:
            dataset = load_lcb_rows(
                dataset_path=None,
                release_version=self.release_version,
            )
            for row in dataset:
                self._cache_hf_task_row(row)
            return

        remaining = set(target_ids) - set(self._cache.keys())
        for row in iter_hf_lcb_rows_stream(
            release_version=self.release_version,
            newest_first=True,
        ):
            task_id = str(row["question_id"])
            if task_id in remaining:
                self._cache_hf_task_row(row)
                remaining.discard(task_id)
            if not remaining:
                break

    def _load_hf_task_cache_batched(self, target_ids: set[str]) -> None:
        remaining = set(target_ids) - set(self._cache.keys())
        if not remaining:
            return

        print(
            f"Fetching {len(remaining)} LiveCodeBench task rows from Hugging Face "
            f"release={self.release_version}..."
        )
        last_progress = len(remaining)

        for shard_index, shard_total, filename, row in iter_hf_lcb_rows_with_files(
            release_version=self.release_version,
            newest_first=True,
        ):
            if filename not in self._hf_logged_shards:
                print(
                    f"  Scanning LiveCodeBench shard {filename} "
                    f"({shard_index}/{shard_total}) for requested task IDs..."
                )
                self._hf_logged_shards.add(filename)
            task_id = str(row["question_id"])
            if task_id not in remaining:
                continue
            self._cache_hf_task_row(row)
            remaining.discard(task_id)
            resolved = len(target_ids) - len(remaining)
            if len(remaining) != last_progress:
                print(
                    f"    Resolved {resolved}/{len(target_ids)} requested tasks; "
                    f"{len(remaining)} still missing."
                )
                last_progress = len(remaining)
            if not remaining:
                break

        if remaining:
            missing_preview = ", ".join(sorted(remaining)[:5])
            raise KeyError(
                f"LiveCodeBench tasks not found in Hugging Face dataset: {missing_preview}"
                + ("..." if len(remaining) > 5 else "")
            )

    def _load_task(self, task_id: str) -> LCBTask:
        if task_id in self._cache:
            return self._cache[task_id]

        if self.dataset_path is None or not self.dataset_path.exists():
            self._load_hf_task_cache({task_id})
            if task_id in self._cache:
                return self._cache[task_id]
            raise KeyError(f"LiveCodeBench task {task_id} not found in Hugging Face dataset")

        raw = json.loads(self._task_path(task_id).read_text())
        task = LCBTask(
            task_id=task_id,
            problem_statement=raw.get("question_content", raw.get("problem_statement", "")),
            difficulty=str(raw.get("difficulty", "medium")),
            starter_code=str(raw.get("starter_code", "")),
            raw=raw,
        )
        self._cache[task_id] = task
        return task

    def _ensure_tasks_loaded(self, task_ids: List[str]) -> None:
        missing = {task_id for task_id in task_ids if task_id not in self._cache}
        if not missing:
            return

        if self.dataset_path is None or not self.dataset_path.exists():
            self._load_hf_task_cache_batched(missing)
            return

        for task_id in sorted(missing):
            self._load_task(task_id)

    def _discover_all_task_ids(self) -> List[str]:
        if self._all_task_ids is not None:
            return self._all_task_ids

        if self.dataset_path is None or not self.dataset_path.exists():
            self._load_hf_task_cache()
            self._all_task_ids = sorted(self._cache.keys())
            return self._all_task_ids

        task_ids: List[str] = []
        for file_path in sorted(self.dataset_path.rglob("*.json")):
            try:
                payload = json.loads(file_path.read_text())
            except Exception:
                continue
            task_id = str(payload.get("task_id", file_path.stem))
            task_ids.append(task_id)

        self._all_task_ids = sorted(set(task_ids), key=str)
        return self._all_task_ids

    def load_tasks(self, task_ids: List[str]) -> List[BenchmarkTask]:
        self._ensure_tasks_loaded(task_ids)
        tasks: List[BenchmarkTask] = []
        for task_id in task_ids:
            task = self._load_task(task_id)
            starter = ""
            if task.starter_code:
                starter = f"\n\nStarter code:\n```python\n{task.starter_code}\n```"

            tasks.append(
                BenchmarkTask(
                    task_id=task_id,
                    benchmark="livecodebench",
                    writer_prompt=self.writer_template.replace("{problem}", task.problem_statement).replace(
                        "{starter_code}",
                        starter,
                    ),
                    reviewer_prompt_template=self.reviewer_template.replace(
                        "{problem}",
                        task.problem_statement,
                    ).replace("{starter_code}", starter),
                    metadata={"difficulty": task.difficulty},
                )
            )
        return tasks

    def _build_custom_outputs(self, records: List[TaskRecord]) -> List[Dict[str, object]]:
        selected = {
            record.task_id: record.final_artifact
            for record in records
            if record.final_artifact and not record.cli_error and not record.timed_out
        }

        outputs = []
        for task_id in self._discover_all_task_ids():
            outputs.append(
                {
                    "question_id": task_id,
                    "code_list": [selected.get(task_id, "")],
                }
            )
        return outputs

    def _extract_pass_map(self, eval_all_path: Path, selected_ids: set[str]) -> Dict[str, bool]:
        payload = json.loads(eval_all_path.read_text())
        results: Dict[str, bool] = {}
        for item in payload:
            task_id = str(item.get("question_id"))
            if task_id not in selected_ids:
                continue

            graded_list = item.get("graded_list", [])
            if isinstance(graded_list, list):
                passed = any(bool(entry) for entry in graded_list)
            else:
                passed = bool(graded_list)
            results[task_id] = passed
        return results

    def _to_problem(self, task_id: str) -> CodeGenerationProblem:
        task = self._load_task(task_id)
        row = dict(task.raw)
        row.pop("task_id", None)
        row["question_id"] = task.task_id
        row["question_content"] = task.problem_statement
        row["difficulty"] = task.difficulty
        row.setdefault("question_title", task.task_id)
        row.setdefault("platform", "atcoder")
        row.setdefault("contest_id", "")
        row.setdefault("contest_date", "1970-01-01T00:00:00")
        row.setdefault("starter_code", task.starter_code)
        row.setdefault("public_test_cases", "[]")
        row.setdefault("private_test_cases", "[]")
        row.setdefault("metadata", "{}")
        return CodeGenerationProblem(**row)

    def evaluate_batch(self, records: List[TaskRecord]) -> Dict[str, bool]:
        """Evaluate only the selected records in-process using upstream metric code."""

        selected_records = [
            record for record in sorted(records, key=lambda item: item.task_id)
            if not record.cli_error and not record.timed_out
        ]
        if not selected_records:
            return {}

        benchmark = [self._to_problem(record.task_id) for record in selected_records]
        eval_samples = [problem.get_evaluation_sample() for problem in benchmark]
        generations = [[record.final_artifact or ""] for record in selected_records]

        sink = io.StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            metrics = codegen_metrics(
                eval_samples,
                generations,
                k_list=[1],
                num_process_evaluate=self.num_process_evaluate,
                timeout=self.timeout,
                debug=False,
            )
        graded = extract_instance_results(metrics[1])

        results: Dict[str, bool] = {}
        for record, graded_list in zip(selected_records, graded):
            results[record.task_id] = any(bool(item) for item in graded_list)
        return results
