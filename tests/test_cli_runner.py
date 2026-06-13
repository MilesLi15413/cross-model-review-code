from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest import mock

from harness.core.cli_runner import CLIRunner, UnsupportedModelError


class CLIRunnerTest(unittest.TestCase):
    def test_claude_build_cmd_includes_medium_effort(self):
        runner = CLIRunner("claude", "claude-opus-4-7", effort="medium", cli_version="claude 1.0")

        with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
            cmd = runner._build_cmd("Reply exactly with OK")

        self.assertEqual(
            [
                "claude",
                "--model",
                "claude-opus-4-7",
                "--print",
                "--output-format",
                "json",
                "--no-session-persistence",
                "--effort",
                "medium",
                "Reply exactly with OK",
            ],
            cmd,
        )

    def test_codex_build_cmd_includes_medium_effort_override(self):
        runner = CLIRunner("codex", "gpt-5.4", effort="medium", cli_version="codex 1.0")

        with mock.patch.object(runner, "_resolve_executable", return_value="codex"):
            cmd = runner._build_cmd("Reply exactly with OK", codex_output_path="/tmp/out.txt")

        self.assertEqual(
            [
                "codex",
                "exec",
                "--model",
                "gpt-5.4",
                "--skip-git-repo-check",
                "--json",
                "--output-last-message",
                "/tmp/out.txt",
                "-c",
                'model_reasoning_effort="medium"',
                "Reply exactly with OK",
            ],
            cmd,
        )

    def test_claude_json_output_is_parsed(self):
        payload = {
            "result": "OK",
            "total_cost_usd": 0.25,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 3,
                "cache_read_input_tokens": 2,
                "cache_creation_input_tokens": 4,
            },
        }
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="claude 1.0")
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                result = runner.run("Reply exactly with OK")

        self.assertEqual("OK", result.response_text)
        self.assertEqual(10, result.input_tokens)
        self.assertEqual(3, result.output_tokens)
        self.assertEqual(2, result.cached_input_tokens)
        self.assertEqual(4, result.cache_creation_input_tokens)
        self.assertEqual(0.25, result.cost_usd)
        self.assertEqual("claude 1.0", result.cli_version)

    def test_claude_run_sets_default_max_output_tokens_env(self):
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="claude 1.0")
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"result": "OK", "usage": {}}),
            stderr="",
        )

        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
                with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed) as run_mock:
                    runner.run("Reply exactly with OK")

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual("200000", env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"])

    def test_claude_run_raises_low_existing_max_output_tokens_env(self):
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="claude 1.0")
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"result": "OK", "usage": {}}),
            stderr="",
        )

        with mock.patch.dict("os.environ", {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000"}, clear=True):
            with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
                with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed) as run_mock:
                    runner.run("Reply exactly with OK")

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual("200000", env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"])

    def test_codex_jsonl_output_is_parsed(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "OK"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 17,
                            "cached_input_tokens": 5,
                            "output_tokens": 8,
                        },
                    }
                ),
            ]
        )
        runner = CLIRunner("codex", "gpt-5.4", cli_version="codex 1.0")
        completed = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

        with mock.patch.object(runner, "_resolve_executable", return_value="codex"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                result = runner.run("Reply exactly with OK")

        self.assertEqual("OK", result.response_text)
        self.assertEqual(17, result.input_tokens)
        self.assertEqual(5, result.cached_input_tokens)
        self.assertEqual(8, result.output_tokens)
        self.assertIsNone(result.cost_usd)

    def test_unsupported_model_raises(self):
        runner = CLIRunner("codex", "bad-model", cli_version="codex 1.0")
        completed = CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="unsupported model",
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="codex"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                with self.assertRaises(UnsupportedModelError):
                    runner.run("prompt")

    def test_rate_limit_retries_until_success_without_pause(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentinel = Path(tmpdir) / "PAUSED"
            events = []
            runner = CLIRunner(
                "claude",
                "claude-opus-4-7",
                cli_version="claude 1.0",
                paused_sentinel_path=str(sentinel),
                status_callback=events.append,
            )
            completed = CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="rate limit exceeded",
            )
            success = CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({"result": "OK", "usage": {}}),
                stderr="",
            )

            with mock.patch(
                "harness.core.cli_runner.subprocess.run",
                side_effect=[completed, completed, success],
            ) as run_mock:
                with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
                    with mock.patch("harness.core.cli_runner.time.sleep", return_value=None) as sleep_mock:
                        result = runner.run("prompt", task_id="task-1", condition_id="C1", turn="writer")

            self.assertEqual("OK", result.response_text)
            self.assertFalse(sentinel.exists())
            self.assertEqual(3, run_mock.call_count)
            self.assertEqual([mock.call(60), mock.call(120)], sleep_mock.call_args_list)
            self.assertEqual(
                [
                    {
                        "event": "rate_limit_wait",
                        "cli": "claude",
                        "model": "claude-opus-4-7",
                        "effort": None,
                        "delay_s": 60,
                        "attempt_index": 1,
                        "retry_number": 2,
                        "task_id": "task-1",
                        "condition_id": "C1",
                        "turn": "writer",
                    },
                    {
                        "event": "rate_limit_wait",
                        "cli": "claude",
                        "model": "claude-opus-4-7",
                        "effort": None,
                        "delay_s": 120,
                        "attempt_index": 2,
                        "retry_number": 3,
                        "task_id": "task-1",
                        "condition_id": "C1",
                        "turn": "writer",
                    },
                ],
                events,
            )

    def test_claude_hit_your_limit_message_waits_and_retries(self):
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="claude 1.0")
        limited = CompletedProcess(
            args=[],
            returncode=1,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": True,
                    "result": "You've hit your limit · resets 9:20pm (America/Los_Angeles)",
                    "usage": {},
                }
            ),
            stderr="",
        )
        success = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"result": "OK", "usage": {}}),
            stderr="",
        )

        with mock.patch(
            "harness.core.cli_runner.subprocess.run",
            side_effect=[limited, success],
        ) as run_mock:
            with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
                with mock.patch("harness.core.cli_runner.time.sleep", return_value=None) as sleep_mock:
                    result = runner.run("prompt")

        self.assertEqual("OK", result.response_text)
        self.assertEqual(2, run_mock.call_count)
        sleep_mock.assert_called_once_with(60)

    def test_timeout_is_raised(self):
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="claude 1.0")
        with mock.patch(
            "harness.core.cli_runner.subprocess.run",
            side_effect=TimeoutExpired(cmd="claude", timeout=300),
        ):
            with mock.patch.object(runner, "_resolve_executable", return_value="claude"):
                with self.assertRaises(TimeoutError):
                    runner.run("prompt")


if __name__ == "__main__":
    unittest.main()
