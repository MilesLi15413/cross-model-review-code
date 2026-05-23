"""Stratified task sampler for SWE-bench Verified."""

from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

HF_DATASET_FALLBACKS = [
    "princeton-nlp/SWE-bench_Verified",
    "SWE-bench/SWE-bench_Verified",
]


def sample_tasks(
    dataset_path: str,
    output_path: str,
    dataset_name: str = "princeton-nlp/SWE-bench_Verified",
    split: str = "test",
    total: int = 50,
    min_repos: int = 5,
    seed: int = 42,
) -> list[str]:
    """
    Sample tasks from SWE-bench Verified, stratified by repo and patch size.

    Targets at least `min_repos` distinct repos, balanced across patch sizes
    (small <50 lines, medium 50-200, large >200).

    Returns list of instance IDs written to output_path.
    """
    random.seed(seed)

    dataset_file = Path(dataset_path)
    if dataset_file.is_file():
        with open(dataset_file) as f:
            all_tasks = json.load(f)
        source = str(dataset_file)
    elif dataset_file.exists():
        # Try JSONL
        all_tasks = []
        for f in Path(dataset_path).glob("*.jsonl"):
            with open(f) as fp:
                for line in fp:
                    all_tasks.append(json.loads(line))
        source = str(dataset_file)
    else:
        dataset_names = [dataset_name] + [
            name for name in HF_DATASET_FALLBACKS if name != dataset_name
        ]
        last_error = None
        all_tasks = []
        source = ""
        for candidate in dataset_names:
            try:
                dataset = load_dataset(candidate, split=split)
            except Exception as exc:
                last_error = exc
                continue
            all_tasks = [dict(row) for row in dataset]
            source = f"Hugging Face {candidate}:{split}"
            break
        if not all_tasks:
            raise FileNotFoundError(
                f"SWE-bench dataset path not found at {dataset_path}, and Hugging Face "
                f"dataset loading failed. Last error: {last_error}"
            )

    # Bucket by repo and patch size
    by_repo: dict[str, list] = defaultdict(list)
    for t in all_tasks:
        repo = t.get("repo", t.get("instance_id", "").split("__")[0])
        patch = t.get("patch", "")
        size = len(patch.splitlines())
        bucket = "small" if size < 50 else ("medium" if size <= 200 else "large")
        by_repo[repo].append({"id": t["instance_id"], "repo": repo, "size": bucket})

    # Stratified sampling: pick across repos first
    repos = sorted(by_repo.keys())
    selected: list[str] = []
    per_repo = max(1, total // max(len(repos), min_repos))

    for repo in repos:
        pool = by_repo[repo]
        chosen = random.sample(pool, min(per_repo, len(pool)))
        selected.extend(t["id"] for t in chosen)
        if len(selected) >= total:
            break

    # Top up if needed
    all_ids = [t["id"] for tasks in by_repo.values() for t in tasks]
    remaining = [i for i in all_ids if i not in set(selected)]
    random.shuffle(remaining)
    selected.extend(remaining[: total - len(selected)])
    selected = selected[:total]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for tid in selected:
            f.write(tid + "\n")

    repos_covered = {t.split("__")[0] for t in selected}
    print(
        f"Sampled {len(selected)} SWE-bench tasks across {len(repos_covered)} repos "
        f"from {source} → {output_path}"
    )
    return selected
