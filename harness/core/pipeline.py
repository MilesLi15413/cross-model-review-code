"""Two-pass writer/reviewer execution pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional

from harness.core.cli_runner import CLIRunner, UsageLimitError
from harness.core.parser import ParseResult, parse_model_response
from harness.core.tracker import CostTracker, TaskRecord


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class BenchmarkTask:
    task_id: str
    benchmark: str
    writer_prompt: str
    reviewer_prompt_template: str
    metadata: Dict[str, object]


@dataclass
class PipelineResult:
    task_id: str
    condition: str
    writer_artifact: str
    reviewer_artifact: str
    final_artifact: str
    record: TaskRecord


class TwoPassPipeline:
    """Runs writer-first and optional reviewer-second prompts for a task."""

    def __init__(
        self,
        writer: CLIRunner,
        reviewer: Optional[CLIRunner],
        tracker: CostTracker,
        condition_id: str,
        per_task_budget_usd: float = 10.0,
        max_task_attempts: int = 4,
    ):
        self.writer = writer
        self.reviewer = reviewer
        self.tracker = tracker
        self.condition_id = condition_id
        self.per_task_budget_usd = per_task_budget_usd
        self.max_task_attempts = max(1, max_task_attempts)

    def _incomplete_reason(self, record: TaskRecord) -> str:
        if record.cli_error:
            return "cli_error"
        if record.timed_out:
            return "timed_out"
        if record.parse_failed:
            return "parse_failed"
        if not (record.final_artifact or "").strip():
            return "empty_final_artifact"
        return "unknown"

    def _cli_error_detail(self, record: TaskRecord) -> str:
        details = []
        writer_error = record.extra.get("writer_error")
        reviewer_error = record.extra.get("reviewer_error")
        if writer_error:
            details.append(f"writer_error:\n{writer_error}")
        if reviewer_error:
            details.append(f"reviewer_error:\n{reviewer_error}")
        return "\n".join(details)

    def _print_incomplete_result(
        self,
        task_id: str,
        reason: str,
        attempt_index: int,
        record: TaskRecord,
        will_retry: bool,
    ) -> None:
        if will_retry:
            message = (
                f"  [{self.condition_id}] {task_id} returned incomplete result "
                f"({reason}); retrying {attempt_index + 1}/{self.max_task_attempts}."
            )
        else:
            message = (
                f"  [{self.condition_id}] {task_id} returned incomplete result "
                f"({reason}); exhausted {attempt_index}/{self.max_task_attempts} attempts."
            )

        if reason == "cli_error":
            detail = self._cli_error_detail(record)
            if detail:
                message = f"{message}\n  Full CLI error:\n{detail}"

        print(message, flush=True)

    def _timeout_retry_runner(self, runner: CLIRunner) -> CLIRunner:
        return CLIRunner(
            cli=runner.cli,
            model=runner.model,
            effort=runner.effort,
            timeout_s=runner.timeout_s * 2,
            paused_sentinel_path=runner.paused_sentinel_path,
            cli_version=runner.get_version(),
            status_callback=runner.status_callback,
        )

    def _apply_writer_result(
        self,
        record: TaskRecord,
        prompt: str,
        parsed: ParseResult,
        run_result,
    ) -> None:
        record.writer_cli = self.writer.cli
        record.writer_effort = self.writer.effort
        record.writer_cli_version = run_result.cli_version
        record.writer_started_at = run_result.started_at
        record.writer_finished_at = run_result.finished_at
        record.writer_prompt_sha256 = _sha256(prompt)
        record.writer_latency_s = run_result.duration_s
        record.writer_input_tokens = run_result.input_tokens
        record.writer_output_tokens = run_result.output_tokens
        record.writer_cached_input_tokens = run_result.cached_input_tokens
        record.writer_cache_creation_input_tokens = run_result.cache_creation_input_tokens
        record.writer_cost_usd = run_result.cost_usd or 0.0
        record.writer_stdout = run_result.raw_stdout
        record.writer_stderr = run_result.raw_stderr
        record.writer_artifact = parsed.artifact
        record.writer_parse_method = parsed.parse_method
        record.writer_has_solution_tag = parsed.has_solution_tag
        record.writer_confidence_note = parsed.confidence_note
        record.writer_confidence_label = parsed.confidence_label

    def _apply_reviewer_result(
        self,
        record: TaskRecord,
        prompt: str,
        parsed: ParseResult,
        run_result,
    ) -> None:
        if self.reviewer is None:
            return

        record.reviewer_cli = self.reviewer.cli
        record.reviewer_effort = self.reviewer.effort
        record.reviewer_cli_version = run_result.cli_version
        record.reviewer_started_at = run_result.started_at
        record.reviewer_finished_at = run_result.finished_at
        record.reviewer_prompt_sha256 = _sha256(prompt)
        record.reviewer_latency_s = run_result.duration_s
        record.reviewer_input_tokens = run_result.input_tokens
        record.reviewer_output_tokens = run_result.output_tokens
        record.reviewer_cached_input_tokens = run_result.cached_input_tokens
        record.reviewer_cache_creation_input_tokens = run_result.cache_creation_input_tokens
        record.reviewer_cost_usd = run_result.cost_usd or 0.0
        record.reviewer_stdout = run_result.raw_stdout
        record.reviewer_stderr = run_result.raw_stderr
        record.reviewer_artifact = parsed.artifact
        record.reviewer_parse_method = parsed.parse_method
        record.reviewer_has_solution_tag = parsed.has_solution_tag

    def _finalize_record(
        self,
        record: TaskRecord,
        writer_parsed: ParseResult,
        reviewer_parsed: Optional[ParseResult] = None,
        reviewer_ran: bool = False,
    ) -> TaskRecord:
        final_artifact = record.writer_artifact
        evaluated_parse = writer_parsed
        evaluated_turn = "writer"

        if reviewer_ran and reviewer_parsed is not None and record.reviewer_artifact:
            final_artifact = record.reviewer_artifact
            evaluated_parse = reviewer_parsed
            evaluated_turn = "reviewer"

        record.final_artifact = final_artifact
        record.evaluated_turn = evaluated_turn
        record.evaluated_parse_method = evaluated_parse.parse_method
        record.evaluated_has_solution_tag = evaluated_parse.has_solution_tag
        record.parse_failed = evaluated_parse.parse_failed
        return self.tracker.finalize(record)

    def run_task(self, task: BenchmarkTask) -> PipelineResult:
        retry_reasons = []
        last_result: Optional[PipelineResult] = None

        for attempt_index in range(1, self.max_task_attempts + 1):
            result = self._run_task_once(task)
            last_result = result
            result.record.extra["attempt_count"] = attempt_index
            if retry_reasons:
                result.record.extra["retry_reasons"] = list(retry_reasons)

            if self.tracker.record_is_complete(result.record):
                return result

            reason = self._incomplete_reason(result.record)
            retry_reasons.append(reason)
            result.record.extra["incomplete_reason"] = reason

            will_retry = attempt_index < self.max_task_attempts
            if will_retry or reason == "cli_error":
                self._print_incomplete_result(
                    task_id=task.task_id,
                    reason=reason,
                    attempt_index=attempt_index,
                    record=result.record,
                    will_retry=will_retry,
                )

        if last_result is None:
            raise RuntimeError("Task retry loop exited without running an attempt.")
        last_result.record.extra["attempt_count"] = self.max_task_attempts
        last_result.record.extra["retry_reasons"] = retry_reasons
        last_result.record.extra["incomplete_reason"] = retry_reasons[-1] if retry_reasons else "unknown"
        return last_result

    def _run_task_once(self, task: BenchmarkTask) -> PipelineResult:
        record = TaskRecord(
            task_id=task.task_id,
            benchmark=task.benchmark,
            condition=self.condition_id,
            writer_model=self.writer.model,
            reviewer_model=self.reviewer.model if self.reviewer else None,
            writer_effort=self.writer.effort,
            reviewer_effort=self.reviewer.effort if self.reviewer else None,
            writer_cli=self.writer.cli,
            reviewer_cli=self.reviewer.cli if self.reviewer else "",
        )

        writer_prompt = task.writer_prompt

        try:
            writer_run = self.writer.run(
                writer_prompt,
                task_id=task.task_id,
                condition_id=self.condition_id,
                turn="writer",
            )
        except TimeoutError:
            record.timed_out = True
            try:
                writer_run = self._timeout_retry_runner(self.writer).run(
                    writer_prompt,
                    task_id=task.task_id,
                    condition_id=self.condition_id,
                    turn="writer",
                )
            except Exception as exc:
                record.cli_error = True
                record.extra["writer_error"] = str(exc)
                empty_parse = ParseResult(
                    artifact="",
                    parse_method="empty",
                    has_solution_tag=False,
                    parse_failed=True,
                )
                self._finalize_record(record, empty_parse)
                return PipelineResult(
                    task_id=task.task_id,
                    condition=self.condition_id,
                    writer_artifact="",
                    reviewer_artifact="",
                    final_artifact="",
                    record=record,
                )
        except UsageLimitError:
            raise
        except Exception as exc:
            record.cli_error = True
            record.extra["writer_error"] = str(exc)
            empty_parse = ParseResult(
                artifact="",
                parse_method="empty",
                has_solution_tag=False,
                parse_failed=True,
            )
            self._finalize_record(record, empty_parse)
            return PipelineResult(
                task_id=task.task_id,
                condition=self.condition_id,
                writer_artifact="",
                reviewer_artifact="",
                final_artifact="",
                record=record,
            )

        writer_parsed = parse_model_response(writer_run.response_text)
        self._apply_writer_result(record, writer_prompt, writer_parsed, writer_run)
        self.tracker.finalize(record)

        if record.total_cost_usd > self.per_task_budget_usd:
            record.budget_exceeded = True
            self._finalize_record(record, writer_parsed)
            return PipelineResult(
                task_id=task.task_id,
                condition=self.condition_id,
                writer_artifact=record.writer_artifact,
                reviewer_artifact="",
                final_artifact=record.final_artifact,
                record=record,
            )

        if self.reviewer is None or not record.writer_artifact:
            self._finalize_record(record, writer_parsed)
            return PipelineResult(
                task_id=task.task_id,
                condition=self.condition_id,
                writer_artifact=record.writer_artifact,
                reviewer_artifact="",
                final_artifact=record.final_artifact,
                record=record,
            )

        reviewer_prompt = task.reviewer_prompt_template.replace(
            "{writer_output}",
            record.writer_artifact,
        )

        try:
            reviewer_run = self.reviewer.run(
                reviewer_prompt,
                task_id=task.task_id,
                condition_id=self.condition_id,
                turn="reviewer",
            )
        except TimeoutError:
            record.timed_out = True
            try:
                reviewer_run = self._timeout_retry_runner(self.reviewer).run(
                    reviewer_prompt,
                    task_id=task.task_id,
                    condition_id=self.condition_id,
                    turn="reviewer",
                )
            except Exception as exc:
                record.cli_error = True
                record.extra["reviewer_error"] = str(exc)
                self._finalize_record(record, writer_parsed)
                return PipelineResult(
                    task_id=task.task_id,
                    condition=self.condition_id,
                    writer_artifact=record.writer_artifact,
                    reviewer_artifact="",
                    final_artifact=record.final_artifact,
                    record=record,
                )
        except UsageLimitError:
            raise
        except Exception as exc:
            record.cli_error = True
            record.extra["reviewer_error"] = str(exc)
            self._finalize_record(record, writer_parsed)
            return PipelineResult(
                task_id=task.task_id,
                condition=self.condition_id,
                writer_artifact=record.writer_artifact,
                reviewer_artifact="",
                final_artifact=record.final_artifact,
                record=record,
            )

        reviewer_parsed = parse_model_response(reviewer_run.response_text)
        self._apply_reviewer_result(record, reviewer_prompt, reviewer_parsed, reviewer_run)
        self._finalize_record(record, writer_parsed, reviewer_parsed, reviewer_ran=True)

        return PipelineResult(
            task_id=task.task_id,
            condition=self.condition_id,
            writer_artifact=record.writer_artifact,
            reviewer_artifact=record.reviewer_artifact,
            final_artifact=record.final_artifact,
            record=record,
        )
