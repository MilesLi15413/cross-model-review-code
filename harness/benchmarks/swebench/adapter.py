"""SWE-bench Verified adapter for prompt construction and deferred evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from datasets import load_dataset

from harness.core.pipeline import BenchmarkTask


SWE_ROOT = Path(__file__).resolve().parents[3] / "external" / "swebench"
HF_DATASET_FALLBACKS = [
    "princeton-nlp/SWE-bench_Verified",
    "SWE-bench/SWE-bench_Verified",
]


def _load_prompts() -> tuple[str, str]:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    return (
        (prompts_dir / "writer_swebench.txt").read_text(),
        (prompts_dir / "reviewer_swebench.txt").read_text(),
    )


@dataclass
class SWETask:
    instance_id: str
    repo: str
    issue_text: str
    base_commit: str
    hints_text: str
    raw: Dict[str, object]


class SWEBenchAdapter:
    """Loads SWE-bench tasks and leaves Docker evaluation to batch_eval.py."""

    def __init__(
        self,
        dataset_path: str,
        dataset_name: str = "princeton-nlp/SWE-bench_Verified",
        split: str = "test",
        max_workers: int = 4,
        timeout: int = 1800,
    ):
        self.dataset_path = Path(dataset_path)
        self.dataset_name = dataset_name
        self.split = split
        self.max_workers = max_workers
        self.timeout = timeout
        self.writer_template, self.reviewer_template = _load_prompts()
        self._index: Optional[Dict[str, SWETask]] = None
        self._dataset_source: Optional[str] = None
        self._check_prerequisites()

    def _check_prerequisites(self) -> None:
        if not SWE_ROOT.exists():
            raise FileNotFoundError(
                f"SWE-bench repo not found at {SWE_ROOT}. "
                "Run setup.sh or clone the benchmark into external/swebench."
            )

    def _build_index(self) -> Dict[str, SWETask]:
        sources: List[Dict[str, object]] = []
        if self.dataset_path.is_file():
            self._dataset_source = str(self.dataset_path)
            sources = json.loads(self.dataset_path.read_text())
        elif self.dataset_path.exists():
            self._dataset_source = str(self.dataset_path)
            for file_path in sorted(self.dataset_path.glob("*.jsonl")):
                for line in file_path.read_text().splitlines():
                    if line.strip():
                        sources.append(json.loads(line))
        else:
            dataset_names = [self.dataset_name] + [
                name for name in HF_DATASET_FALLBACKS if name != self.dataset_name
            ]
            last_error = None
            for dataset_name in dataset_names:
                print(
                    f"SWE-bench dataset path not found at {self.dataset_path}. "
                    f"Trying Hugging Face dataset {dataset_name} split={self.split}..."
                )
                try:
                    dataset = load_dataset(dataset_name, split=self.split)
                except Exception as exc:
                    last_error = exc
                    continue
                self._dataset_source = f"{dataset_name}:{self.split}"
                sources = [dict(row) for row in dataset]
                break
            if not sources:
                raise FileNotFoundError(
                    f"SWE-bench dataset path not found locally at {self.dataset_path}, "
                    f"and Hugging Face dataset loading also failed. Last error: {last_error}"
                )

        tasks: Dict[str, SWETask] = {}
        for raw in sources:
            instance_id = raw["instance_id"]
            tasks[instance_id] = SWETask(
                instance_id=instance_id,
                repo=str(raw.get("repo", "")),
                issue_text=str(raw.get("problem_statement", raw.get("issue", ""))),
                base_commit=str(raw.get("base_commit", "")),
                hints_text=str(raw.get("hints_text", "")),
                raw=raw,
            )
        return tasks

    @property
    def index(self) -> Dict[str, SWETask]:
        if self._index is None:
            self._index = self._build_index()
            print(
                f"Loaded {len(self._index)} SWE-bench tasks "
                f"from {self._dataset_source or 'unknown source'}."
            )
        return self._index

    def load_tasks(self, task_ids: List[str]) -> List[BenchmarkTask]:
        tasks: List[BenchmarkTask] = []
        for task_id in task_ids:
            task = self.index[task_id]
            hints = f"\n\nHints:\n{task.hints_text}" if task.hints_text else ""
            tasks.append(
                BenchmarkTask(
                    task_id=task_id,
                    benchmark="swebench",
                    writer_prompt=self.writer_template.replace("{repo}", task.repo).replace(
                        "{issue}",
                        task.issue_text,
                    ).replace("{hints}", hints),
                    reviewer_prompt_template=self.reviewer_template.replace(
                        "{repo}",
                        task.repo,
                    ).replace("{issue}", task.issue_text).replace("{hints}", hints),
                    metadata={"repo": task.repo, "base_commit": task.base_commit},
                )
            )
        return tasks

    def evaluate_task(self, task: BenchmarkTask, artifact: str):
        return None
