"""Cost, record, and checkpoint tracking helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class TaskRecord:
    task_id: str
    condition: str
    benchmark: str
    writer_model: str
    reviewer_model: Optional[str]
    writer_effort: Optional[str] = None
    reviewer_effort: Optional[str] = None
    writer_cli: str = ""
    reviewer_cli: str = ""
    writer_cli_version: str = ""
    reviewer_cli_version: str = ""
    writer_started_at: str = ""
    writer_finished_at: str = ""
    reviewer_started_at: str = ""
    reviewer_finished_at: str = ""
    writer_prompt_sha256: str = ""
    reviewer_prompt_sha256: str = ""
    writer_latency_s: float = 0.0
    reviewer_latency_s: float = 0.0
    total_latency_s: float = 0.0
    writer_input_tokens: int = 0
    writer_output_tokens: int = 0
    writer_cached_input_tokens: int = 0
    writer_cache_creation_input_tokens: int = 0
    reviewer_input_tokens: int = 0
    reviewer_output_tokens: int = 0
    reviewer_cached_input_tokens: int = 0
    reviewer_cache_creation_input_tokens: int = 0
    writer_cost_usd: float = 0.0
    reviewer_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    writer_parse_method: str = ""
    reviewer_parse_method: str = ""
    writer_has_solution_tag: bool = False
    reviewer_has_solution_tag: bool = False
    evaluated_turn: str = "writer"
    evaluated_parse_method: str = ""
    evaluated_has_solution_tag: bool = False
    parse_failed: bool = False
    timed_out: bool = False
    cli_error: bool = False
    budget_exceeded: bool = False
    passed: Optional[bool] = None
    writer_passed: Optional[bool] = None
    writer_stdout: str = ""
    writer_stderr: str = ""
    reviewer_stdout: str = ""
    reviewer_stderr: str = ""
    writer_artifact: str = ""
    reviewer_artifact: str = ""
    final_artifact: str = ""
    writer_confidence_note: Optional[str] = None
    writer_confidence_label: Optional[str] = None
    extra: Dict[str, object] = field(default_factory=dict)


class CostTracker:
    """Computes fallback costs and manages checkpoint serialization."""

    def __init__(self, pricing_path: str = "experiments/configs/pricing.yaml"):
        self.pricing: Dict[str, Dict[str, float]] = {}
        pricing_file = Path(pricing_path)
        if pricing_file.exists():
            self.pricing = yaml.safe_load(pricing_file.read_text()) or {}

    def compute_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> float:
        """Compute cost in USD using pricing.yaml rates per 1M tokens."""

        rates = self.pricing.get(model, {})
        if not rates:
            return 0.0

        input_rate = rates.get("input_per_1m", 0.0)
        output_rate = rates.get("output_per_1m", 0.0)
        cached_input_rate = rates.get("cached_input_per_1m", input_rate)
        cache_creation_rate = rates.get("cache_creation_input_per_1m", input_rate)
        long_context_threshold = int(rates.get("long_context_threshold_tokens", 0) or 0)
        billable_input_tokens = input_tokens + cached_input_tokens + cache_creation_input_tokens
        if long_context_threshold and billable_input_tokens > long_context_threshold:
            input_multiplier = rates.get("long_context_input_multiplier", 1.0)
            output_multiplier = rates.get("long_context_output_multiplier", 1.0)
            input_rate *= input_multiplier
            cached_input_rate *= input_multiplier
            cache_creation_rate *= input_multiplier
            output_rate *= output_multiplier

        return (
            (input_tokens * input_rate)
            + (output_tokens * output_rate)
            + (cached_input_tokens * cached_input_rate)
            + (cache_creation_input_tokens * cache_creation_rate)
        ) / 1_000_000

    def finalize(self, record: TaskRecord) -> TaskRecord:
        """Fill in computed totals if the CLI did not provide them."""

        if record.writer_model and record.writer_cost_usd == 0.0:
            record.writer_cost_usd = self.compute_cost(
                record.writer_model,
                record.writer_input_tokens,
                record.writer_output_tokens,
                cached_input_tokens=record.writer_cached_input_tokens,
                cache_creation_input_tokens=record.writer_cache_creation_input_tokens,
            )

        if record.reviewer_model and record.reviewer_cost_usd == 0.0:
            record.reviewer_cost_usd = self.compute_cost(
                record.reviewer_model,
                record.reviewer_input_tokens,
                record.reviewer_output_tokens,
                cached_input_tokens=record.reviewer_cached_input_tokens,
                cache_creation_input_tokens=record.reviewer_cache_creation_input_tokens,
            )

        record.total_latency_s = record.writer_latency_s + record.reviewer_latency_s
        record.total_cost_usd = record.writer_cost_usd + record.reviewer_cost_usd
        return record

    def save(self, record: TaskRecord, checkpoint_dir: str) -> str:
        checkpoint_path = Path(checkpoint_dir)
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        path = checkpoint_path / f"{record.task_id}__{record.condition}.json"
        path.write_text(json.dumps(asdict(record), indent=2))
        return str(path)

    def load_all(self, checkpoint_dir: str) -> List[TaskRecord]:
        records: List[TaskRecord] = []
        checkpoint_path = Path(checkpoint_dir)
        if not checkpoint_path.exists():
            return records

        for file_path in sorted(checkpoint_path.glob("*.json")):
            payload = json.loads(file_path.read_text())
            records.append(TaskRecord(**payload))
        return records

    def load_one(self, task_id: str, condition: str, checkpoint_dir: str) -> Optional[TaskRecord]:
        path = Path(checkpoint_dir) / f"{task_id}__{condition}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return TaskRecord(**payload)

    def record_is_complete(self, record: TaskRecord) -> bool:
        """Return whether a checkpointed record is complete enough to skip on resume.

        We rerun true execution failures automatically on resume, but we preserve
        successful inference outputs whose benchmark evaluation is still pending.
        A record must contain a parsed final artifact; otherwise an interrupted or
        malformed response would be counted as finished and skipped forever.
        """

        if record.cli_error or record.timed_out:
            return False
        if record.parse_failed:
            return False
        if not (record.final_artifact or "").strip():
            return False
        return True

    def is_done(self, task_id: str, condition: str, checkpoint_dir: str) -> bool:
        record = self.load_one(task_id, condition, checkpoint_dir)
        if record is None:
            return False
        return self.record_is_complete(record)
