"""LiveCodeBench dataset helpers for local JSON and HF JSONL sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from huggingface_hub.errors import RevisionNotFoundError
from huggingface_hub import hf_hub_download, hf_hub_url, list_repo_files


HF_LCB_REPO = "livecodebench/code_generation_lite"


def _hf_shard_sort_key(filename: str) -> tuple[int, str]:
    stem = Path(filename).stem
    suffix = stem.replace("test", "")
    return (int(suffix) if suffix.isdigit() else 1, filename)


def _load_local_json_rows(dataset_dir: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for file_path in sorted(dataset_dir.glob("*.json")):
        rows.append(json.loads(file_path.read_text()))
    return rows


def _load_hf_jsonl_rows(release_version: str = "release_latest") -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for _, _, _, local_path in iter_hf_lcb_jsonl_files(release_version=release_version):
        with open(local_path) as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def iter_hf_lcb_jsonl_files(
    release_version: str = "release_latest",
    newest_first: bool = False,
):
    revision = None if release_version == "release_latest" else release_version
    try:
        files = list_repo_files(
            HF_LCB_REPO,
            repo_type="dataset",
            revision=revision,
        )
    except RevisionNotFoundError:
        files = list_repo_files(
            HF_LCB_REPO,
            repo_type="dataset",
        )
        revision = None

    jsonl_files = sorted(
        (file_path for file_path in files if file_path.endswith(".jsonl")),
        key=_hf_shard_sort_key,
        reverse=newest_first,
    )
    if not jsonl_files:
        raise RuntimeError(
            f"No JSONL shards found in {HF_LCB_REPO} for revision {release_version}."
        )

    for index, filename in enumerate(jsonl_files, start=1):
        local_path = hf_hub_download(
            repo_id=HF_LCB_REPO,
            repo_type="dataset",
            filename=filename,
            revision=revision,
        )
        yield index, len(jsonl_files), filename, local_path


def iter_hf_lcb_rows_with_files(
    release_version: str = "release_latest",
    newest_first: bool = False,
):
    """Yield rows together with the shard filename they came from."""

    for index, total, filename, local_path in iter_hf_lcb_jsonl_files(
        release_version=release_version,
        newest_first=newest_first,
    ):
        with open(local_path) as handle:
            for line in handle:
                if line.strip():
                    yield index, total, filename, json.loads(line)


def iter_hf_lcb_rows_stream(
    release_version: str = "release_latest",
    newest_first: bool = False,
):
    revision = None if release_version == "release_latest" else release_version
    try:
        files = list_repo_files(
            HF_LCB_REPO,
            repo_type="dataset",
            revision=revision,
        )
    except RevisionNotFoundError:
        files = list_repo_files(
            HF_LCB_REPO,
            repo_type="dataset",
        )
        revision = None

    jsonl_files = sorted(
        (file_path for file_path in files if file_path.endswith(".jsonl")),
        key=_hf_shard_sort_key,
        reverse=newest_first,
    )
    if not jsonl_files:
        raise RuntimeError(
            f"No JSONL shards found in {HF_LCB_REPO} for revision {release_version}."
        )

    for filename in jsonl_files:
        url = hf_hub_url(
            repo_id=HF_LCB_REPO,
            repo_type="dataset",
            filename=filename,
            revision=revision,
        )
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    yield json.loads(line)


def load_lcb_rows(
    dataset_path: Optional[str] = None,
    release_version: str = "release_latest",
) -> List[Dict[str, object]]:
    dataset_dir = Path(dataset_path) if dataset_path else None
    if dataset_dir and dataset_dir.exists():
        return _load_local_json_rows(dataset_dir)
    return _load_hf_jsonl_rows(release_version=release_version)


def filter_lcb_rows(rows: Iterable[Dict[str, object]], min_date: Optional[str] = None) -> List[Dict[str, object]]:
    filtered: List[Dict[str, object]] = []
    for row in rows:
        contest_date = str(row.get("contest_date", row.get("start_date", "")))
        if min_date and contest_date and contest_date < min_date:
            continue
        filtered.append(dict(row))
    return filtered
