"""Stratified task sampler for LiveCodeBench."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

from harness.benchmarks.livecodebench.dataset_loader import (
    filter_lcb_rows,
    iter_hf_lcb_rows_with_files,
    load_lcb_rows,
)


DIFFICULTY_TARGETS = {"easy": 30, "medium": 40, "hard": 30}


def _normalize_difficulty(difficulty: str | None) -> str | None:
    if difficulty is None:
        return None
    normalized = difficulty.strip().lower()
    if normalized in {"easy", "medium", "hard"}:
        return normalized
    raise ValueError(f"Unsupported LiveCodeBench difficulty filter: {difficulty}")


def _select_by_difficulty(
    tasks_by_difficulty: dict[str, list[str]],
    total: int,
    selected_difficulty: str | None,
) -> list[str]:
    if selected_difficulty is not None:
        pool = tasks_by_difficulty[selected_difficulty]
        return random.sample(pool, min(total, len(pool)))

    ratios = {"easy": 0.30, "medium": 0.40, "hard": 0.30}
    targets = {difficulty: round(total * ratio) for difficulty, ratio in ratios.items()}
    targets["hard"] = total - targets["easy"] - targets["medium"]

    selected: list[str] = []
    for difficulty in ("easy", "medium", "hard"):
        n = targets[difficulty]
        pool = tasks_by_difficulty[difficulty]
        selected.extend(random.sample(pool, min(n, len(pool))))
    return selected[:total]


def _target_counts(total: int, difficulty: str | None) -> dict[str, int]:
    if difficulty is not None:
        targets = {"easy": 0, "medium": 0, "hard": 0}
        targets[difficulty] = total
        return targets

    ratios = {"easy": 0.30, "medium": 0.40, "hard": 0.30}
    targets = {level: round(total * ratio) for level, ratio in ratios.items()}
    targets["hard"] = total - targets["easy"] - targets["medium"]
    return targets


def _progress():
    try:
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )
    except ImportError:
        return None

    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description:<28}"),
        BarColumn(bar_width=24),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[dim]{task.fields[status]}"),
        refresh_per_second=2,
    )


def _sample_from_local_json(
    dataset_dir: Path,
    total: int,
    min_date: str,
    seed: int,
    difficulty: str | None,
) -> list[str]:
    random.seed(seed)

    tasks_by_difficulty: dict[str, list] = {"easy": [], "medium": [], "hard": []}
    files = sorted(dataset_dir.glob("*.json"))
    progress = _progress()

    def scan_files():
        for file_path in files:
            with open(file_path) as fp:
                task = json.load(fp)

            contest_date = task.get("contest_date", task.get("start_date", ""))
            if contest_date and contest_date < min_date:
                yield file_path
                continue

            level = task.get("difficulty", "medium").lower()
            if level not in tasks_by_difficulty:
                level = "medium"
            tasks_by_difficulty[level].append(task["task_id"])
            yield file_path

    if progress is None:
        for _ in scan_files():
            pass
    else:
        with progress:
            task_id = progress.add_task(
                "Scanning local LCB tasks",
                total=len(files),
                status=f"target={total}" + (f" difficulty={difficulty}" if difficulty else ""),
            )
            for file_path in scan_files():
                progress.update(task_id, advance=1, status=file_path.name)

    return _select_by_difficulty(tasks_by_difficulty, total, difficulty)


def _sample_from_huggingface(
    total: int,
    min_date: str,
    seed: int,
    release_version: str = "release_latest",
    difficulty: str | None = None,
) -> list[str]:
    random.seed(seed)

    tasks_by_difficulty: dict[str, list] = {"easy": [], "medium": [], "hard": []}
    targets = _target_counts(total, difficulty)
    progress = _progress()
    scanned = 0
    current_shard = None

    def accepted_count() -> int:
        return sum(len(tasks_by_difficulty[level]) for level in targets)

    def status_text(filename: str | None = None) -> str:
        breakdown = " ".join(
            f"{level[0]}={len(tasks_by_difficulty[level])}/{targets[level]}"
            for level in ("easy", "medium", "hard")
            if targets[level]
        )
        shard = f" | {filename}" if filename else ""
        return f"scanned={scanned} {breakdown}{shard}".strip()

    if progress is None:
        print(
            f"Sampling LiveCodeBench tasks from Hugging Face release={release_version} "
            f"target={total}" + (f" difficulty={difficulty}" if difficulty else ""),
            flush=True,
        )

    with progress if progress is not None else _NullContext() as active_progress:
        found_task = None
        shard_task = None
        if active_progress is not None:
            found_task = active_progress.add_task(
                "Sampling LCB tasks",
                total=total,
                status=status_text(),
            )
            shard_task = active_progress.add_task(
                "Scanning HF shards",
                total=None,
                status=f"release={release_version}",
            )

        for shard_index, shard_total, filename, row in iter_hf_lcb_rows_with_files(
            release_version=release_version,
            newest_first=True,
        ):
            if filename != current_shard:
                current_shard = filename
                if active_progress is not None:
                    active_progress.update(
                        shard_task,
                        total=shard_total,
                        completed=shard_index - 1,
                        status=filename,
                    )
                else:
                    print(
                        f"  Scanning LiveCodeBench shard {filename} "
                        f"({shard_index}/{shard_total})...",
                        flush=True,
                    )

            scanned += 1
            task = filter_lcb_rows([row], min_date=min_date)
            if not task:
                continue
            task = task[0]
            task_difficulty = str(task.get("difficulty", "medium")).lower()
            if task_difficulty not in tasks_by_difficulty:
                task_difficulty = "medium"
            if len(tasks_by_difficulty[task_difficulty]) >= targets[task_difficulty]:
                continue
            tasks_by_difficulty[task_difficulty].append(str(task["question_id"]))
            if active_progress is not None:
                active_progress.update(
                    found_task,
                    completed=accepted_count(),
                    status=status_text(filename),
                )
            else:
                print(f"    Selected {accepted_count()}/{total}: {status_text()}", flush=True)

            if all(len(tasks_by_difficulty[level]) >= targets[level] for level in targets):
                break

        if active_progress is not None and shard_task is not None:
            active_progress.update(shard_task, completed=shard_total if "shard_total" in locals() else 0)

    return _select_by_difficulty(tasks_by_difficulty, total, difficulty)


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False


def sample_tasks(
    dataset_path: str,
    output_path: str,
    total: int = 100,
    min_date: str = "2025-01-01",
    seed: int = 42,
    release_version: str = "release_latest",
    difficulty: str | None = None,
) -> list[str]:
    """
    Sample tasks from LiveCodeBench dataset.

    Stratifies by difficulty (30/40/30) by default, or filters to a single
    difficulty if requested. Always filters to post-2025 problems to reduce
    contamination risk.

    Returns list of task IDs written to output_path.
    """
    difficulty = _normalize_difficulty(difficulty)
    dataset_dir = Path(dataset_path)
    if dataset_dir.exists():
        selected = _sample_from_local_json(
            dataset_dir=dataset_dir,
            total=total,
            min_date=min_date,
            seed=seed,
            difficulty=difficulty,
        )
        source = str(dataset_dir)
    else:
        selected = _sample_from_huggingface(
            total=total,
            min_date=min_date,
            seed=seed,
            release_version=release_version,
            difficulty=difficulty,
        )
        source = f"Hugging Face release={release_version}"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for tid in selected:
            f.write(tid + "\n")

    print(f"Sampled {len(selected)} tasks from {source} → {output_path}")
    if difficulty is not None:
        breakdown = {"easy": 0, "medium": 0, "hard": 0}
        breakdown[difficulty] = len(selected)
    else:
        breakdown = {
            "easy": round(len(selected) * 0.30),
            "medium": round(len(selected) * 0.40),
            "hard": len(selected) - round(len(selected) * 0.30) - round(len(selected) * 0.40),
        }
    print(f"  Difficulty breakdown: {breakdown}")
    return selected
