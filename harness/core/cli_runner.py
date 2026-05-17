"""Subprocess wrappers for Claude Code and Codex CLIs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional


RATE_LIMIT_PATTERNS = [
    r"rate.?limit",
    r"usage.?limit",
    r"hit.?your.?limit",
    r"429",
    r"quota.?exceeded",
    r"try.?again",
    r"too.?many.?requests",
    r"overloaded",
]

UNSUPPORTED_MODEL_PATTERNS = [
    "unknown model",
    "invalid model",
    "model not found",
    "unsupported model",
]

AUTH_PATTERNS = [
    "not logged in",
    "authentication",
    "unauthorized",
    "forbidden",
    "api key",
    "login required",
]

RATE_LIMIT_RETRY_DELAYS = [60, 120, 300, 600, 900]
CLAUDE_CODE_MAX_OUTPUT_TOKENS_ENV = "CLAUDE_CODE_MAX_OUTPUT_TOKENS"
DEFAULT_CLAUDE_CODE_MAX_OUTPUT_TOKENS = "200000"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches_any(text: str, patterns: List[str]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _hashable_cli_key(cli: str, model: str, effort: Optional[str] = None) -> str:
    return f"{cli}:{model}:{effort or ''}"


def _rate_limit_retry_delay(attempt_index: int) -> int:
    """Return the wait before the next attempt after a rate-limit response."""

    delay_index = min(max(attempt_index - 1, 0), len(RATE_LIMIT_RETRY_DELAYS) - 1)
    return RATE_LIMIT_RETRY_DELAYS[delay_index]


class CLIError(Exception):
    """Base exception for CLI failures."""


class UnsupportedModelError(CLIError):
    """Raised when a CLI rejects a requested model."""


class AuthenticationError(CLIError):
    """Raised when a CLI session is not authenticated."""


class MissingCLIError(CLIError):
    """Raised when a required CLI executable cannot be found."""


class UsageLimitError(CLIError):
    """Reserved for explicit/manual pause flows, not normal rate-limit waiting."""

    def __init__(self, message: str, pause_info: Optional[Dict[str, object]] = None):
        super().__init__(message)
        self.pause_info = pause_info or {}


@dataclass
class RunResult:
    response_text: str
    raw_stdout: str
    raw_stderr: str
    exit_code: int
    duration_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: Optional[float] = None
    cli_version: str = ""
    started_at: str = ""
    finished_at: str = ""


class CLIRunner:
    """Thin runner around the Claude Code and Codex CLIs."""

    def __init__(
        self,
        cli: str,
        model: str,
        effort: Optional[str] = None,
        timeout_s: int = 300,
        paused_sentinel_path: Optional[str] = None,
        cli_version: str = "",
        status_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ):
        self.cli = cli
        self.model = model
        self.effort = effort
        self.timeout_s = timeout_s
        self.paused_sentinel_path = paused_sentinel_path
        self._cli_version = cli_version
        self._resolved_executable: Optional[str] = None
        self.status_callback = status_callback

    def _resolve_executable(self) -> str:
        if self._resolved_executable:
            return self._resolved_executable

        candidates = [self.cli]
        if self.cli == "codex":
            candidates.extend(
                [
                    "/Applications/Codex.app/Contents/Resources/codex",
                    str(Path.home() / ".local" / "bin" / "codex"),
                    "/opt/homebrew/bin/codex",
                    "/usr/local/bin/codex",
                ]
            )
        elif self.cli == "claude":
            candidates.extend(
                [
                    str(Path.home() / ".local" / "bin" / "claude"),
                    "/opt/homebrew/bin/claude",
                    "/usr/local/bin/claude",
                ]
            )

        for candidate in candidates:
            resolved = shutil.which(candidate) if not str(candidate).startswith("/") else candidate
            if resolved and Path(resolved).exists():
                self._resolved_executable = resolved
                return resolved

        raise MissingCLIError(
            f"Could not find the '{self.cli}' executable. "
            f"Tried PATH lookup and common install locations: {candidates[1:]}"
        )

    def get_version(self) -> str:
        if self._cli_version:
            return self._cli_version

        result = subprocess.run(
            [self._resolve_executable(), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        version_text = (result.stdout or result.stderr).strip()
        if not version_text:
            version_text = "unknown"
        self._cli_version = version_text
        return self._cli_version

    def _build_cmd(self, prompt: str, codex_output_path: Optional[str] = None) -> List[str]:
        executable = self._resolve_executable()
        if self.cli == "claude":
            cmd = [
                executable,
                "--model",
                self.model,
                "--print",
                "--output-format",
                "json",
                "--no-session-persistence",
            ]
            if self.effort:
                cmd.extend(["--effort", self.effort])
            cmd.append(prompt)
            return cmd

        if codex_output_path is None:
            raise ValueError("codex_output_path is required for Codex runs")

        cmd = [
            executable,
            "exec",
            "--model",
            self.model,
            "--skip-git-repo-check",
            "--json",
            "--output-last-message",
            codex_output_path,
        ]
        if self.effort:
            cmd.extend(["-c", f'model_reasoning_effort="{self.effort}"'])
        cmd.append(prompt)
        return cmd

    def _subprocess_env(self) -> Optional[Dict[str, str]]:
        if self.cli != "claude":
            return None

        env = os.environ.copy()
        configured = env.get(CLAUDE_CODE_MAX_OUTPUT_TOKENS_ENV)
        try:
            configured_int = int(configured) if configured else 0
        except ValueError:
            configured_int = 0
        default_int = int(DEFAULT_CLAUDE_CODE_MAX_OUTPUT_TOKENS)
        if configured_int < default_int:
            env[CLAUDE_CODE_MAX_OUTPUT_TOKENS_ENV] = DEFAULT_CLAUDE_CODE_MAX_OUTPUT_TOKENS
        return env

    def _build_pause_info(
        self,
        attempt_count: int,
        task_id: Optional[str],
        condition_id: Optional[str],
        turn: Optional[str],
    ) -> Dict[str, object]:
        return {
            "timestamp": _now_iso(),
            "cli": self.cli,
            "model": self.model,
            "effort": self.effort,
            "attempt_count": attempt_count,
            "blocked_condition": condition_id,
            "last_task_id": task_id,
            "turn": turn,
            "cli_version": self.get_version(),
        }

    def _write_pause_sentinel(self, pause_info: Dict[str, object]) -> None:
        if not self.paused_sentinel_path:
            return

        sentinel_path = Path(self.paused_sentinel_path)
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(json.dumps(pause_info, indent=2))

    def _parse_claude_response(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_s: float,
        started_at: str,
        finished_at: str,
    ) -> RunResult:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise CLIError(f"Failed to parse Claude JSON output: {exc}") from exc

        usage = payload.get("usage", {})
        response_text = payload.get("result", "")
        return RunResult(
            response_text=response_text,
            raw_stdout=stdout,
            raw_stderr=stderr,
            exit_code=exit_code,
            duration_s=duration_s,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cached_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(
                usage.get("cache_creation_input_tokens", 0) or 0
            ),
            cost_usd=payload.get("total_cost_usd"),
            cli_version=self.get_version(),
            started_at=started_at,
            finished_at=finished_at,
        )

    def _parse_codex_response(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_s: float,
        started_at: str,
        finished_at: str,
        output_last_message_path: str,
    ) -> RunResult:
        response_text = ""
        usage: Dict[str, object] = {}
        ignored_lines: List[str] = []

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith("{"):
                ignored_lines.append(raw_line)
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                ignored_lines.append(raw_line)
                continue

            event_type = event.get("type")
            if event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    response_text = item.get("text", "") or response_text
            elif event_type == "turn.completed":
                usage = event.get("usage", {}) or usage
            elif event_type == "error":
                raise CLIError(f"Codex returned an error event: {event}")

        last_message_file = Path(output_last_message_path)
        if last_message_file.exists():
            file_text = last_message_file.read_text().strip()
            if file_text:
                response_text = file_text

        if not response_text:
            raise CLIError(
                "Failed to extract the final Codex response from --json events. "
                f"Ignored lines: {ignored_lines[:5]}"
            )

        return RunResult(
            response_text=response_text,
            raw_stdout=stdout,
            raw_stderr=stderr,
            exit_code=exit_code,
            duration_s=duration_s,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cached_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
            cache_creation_input_tokens=0,
            cost_usd=None,
            cli_version=self.get_version(),
            started_at=started_at,
            finished_at=finished_at,
        )

    def run(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        condition_id: Optional[str] = None,
        turn: Optional[str] = None,
    ) -> RunResult:
        attempt_index = 1
        while True:
            started_at = _now_iso()
            start_monotonic = time.monotonic()
            codex_output_path = None

            if self.cli == "codex":
                tmpdir = tempfile.TemporaryDirectory(prefix="codex-cli-run-")
                codex_output_path = str(Path(tmpdir.name) / "last_message.txt")
            else:
                tmpdir = None

            cmd = self._build_cmd(prompt, codex_output_path)

            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    check=False,
                    env=self._subprocess_env(),
                )
            except subprocess.TimeoutExpired as exc:
                if tmpdir is not None:
                    tmpdir.cleanup()
                raise TimeoutError(
                    f"{self.cli} timed out after {self.timeout_s}s on attempt {attempt_index}"
                ) from exc

            duration_s = time.monotonic() - start_monotonic
            finished_at = _now_iso()
            combined_output = f"{completed.stdout}\n{completed.stderr}"

            try:
                if _matches_any(combined_output, UNSUPPORTED_MODEL_PATTERNS):
                    raise UnsupportedModelError(
                        f"Unsupported model '{self.model}' on {self.cli}. "
                        f"Output: {(completed.stderr or completed.stdout).strip()}"
                    )

                if _matches_any(combined_output, AUTH_PATTERNS):
                    raise AuthenticationError(
                        f"Authentication failed for {self.cli}. "
                        f"Output: {(completed.stderr or completed.stdout).strip()}"
                    )

                if _matches_any(combined_output, RATE_LIMIT_PATTERNS):
                    delay = _rate_limit_retry_delay(attempt_index)
                    retry_number = attempt_index + 1
                    if self.status_callback:
                        self.status_callback(
                            {
                                "event": "rate_limit_wait",
                                "cli": self.cli,
                                "model": self.model,
                                "effort": self.effort,
                                "delay_s": delay,
                                "attempt_index": attempt_index,
                                "retry_number": retry_number,
                                "task_id": task_id,
                                "condition_id": condition_id,
                                "turn": turn,
                            }
                        )
                    context = " ".join(
                        part
                        for part in [
                            f"condition={condition_id}" if condition_id else "",
                            f"task={task_id}" if task_id else "",
                            f"turn={turn}" if turn else "",
                        ]
                        if part
                    )
                    if tmpdir is not None:
                        tmpdir.cleanup()
                        tmpdir = None
                    print(
                        f"  Waiting on usage limit for {self.cli}/{self.model}"
                        + (f" effort={self.effort}" if self.effort else "")
                        + ". "
                        f"Retry #{retry_number} in {delay}s."
                        + (f" {context}" if context else ""),
                        flush=True,
                    )
                    time.sleep(delay)
                    attempt_index += 1
                    continue

                if completed.returncode != 0:
                    raise CLIError(
                        f"{self.cli} exited with code {completed.returncode}\n"
                        f"stdout: {completed.stdout.strip()}\n"
                        f"stderr: {completed.stderr.strip()}"
                    )

                if self.cli == "claude":
                    return self._parse_claude_response(
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                        exit_code=completed.returncode,
                        duration_s=duration_s,
                        started_at=started_at,
                        finished_at=finished_at,
                    )

                return self._parse_codex_response(
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    exit_code=completed.returncode,
                    duration_s=duration_s,
                    started_at=started_at,
                    finished_at=finished_at,
                    output_last_message_path=codex_output_path or "",
                )
            finally:
                if tmpdir is not None:
                    tmpdir.cleanup()


def cli_model_key(cli: str, model: str, effort: Optional[str] = None) -> str:
    """Stable key for deduplicating CLI/model/effort checks."""

    return _hashable_cli_key(cli, model, effort)
