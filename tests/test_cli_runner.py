from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest import mock

from harness.core.cli_runner import (
    AuthenticationError,
    CLIError,
    CLIRunner,
    UnsupportedModelError,
    UsageLimitError,
)


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

    def test_gemini_build_cmd(self):
        runner = CLIRunner("gemini", "gemini-3.8-flash", cli_version="0.65.0")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            cmd = runner._build_cmd("Reply exactly with OK")

        self.assertEqual(
            [
                "gemini",
                "--model",
                "gemini-3.8-flash",
                "--output-format",
                "json",
                "--skip-trust",
                "--prompt",
                "Reply exactly with OK",
            ],
            cmd,
        )

    def test_gemini_rejects_unknown_effort(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", effort="max", cli_version="0.65.0")

        with self.assertRaises(ValueError):
            runner._gemini_settings()

    def test_gemini_high_effort_sets_thinking_level_and_blocks_tools(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", effort="high", cli_version="0.65.0")

        settings = runner._gemini_settings()

        override = settings["modelConfigs"]["customOverrides"][0]
        self.assertEqual({"model": "gemini-3.1-pro-preview"}, override["match"])
        self.assertEqual(
            "HIGH",
            override["modelConfig"]["generateContentConfig"]["thinkingConfig"]["thinkingLevel"],
        )
        self.assertEqual([], settings["tools"]["core"])
        self.assertEqual(1, len(settings["mcp"]["allowed"]))

    def test_gemini_runs_in_empty_dir_with_system_settings(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", effort="high", cli_version="0.65.0")
        payload = {
            "response": "OK",
            "stats": {"models": {"gemini-3.1-pro-preview": {"tokens": {"prompt": 10, "candidates": 1}}}},
        }
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cwd_files"] = list(Path(kwargs["cwd"]).iterdir())
            settings_path = kwargs["env"]["GEMINI_CLI_SYSTEM_SETTINGS_PATH"]
            seen["settings"] = json.loads(Path(settings_path).read_text())
            return CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", side_effect=fake_run):
                result = runner.run("prompt")

        self.assertEqual([], seen["cwd_files"])
        self.assertEqual([], seen["settings"]["tools"]["core"])
        self.assertEqual("HIGH", result.runtime_settings["thinking_level"])
        self.assertEqual(["gemini-3.1-pro-preview"], result.runtime_settings["models_used"])

    def test_gemini_fallback_to_another_model_is_an_error(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        payload = {
            "response": "OK",
            "stats": {"models": {"gemini-3.8-flash": {"tokens": {"prompt": 10, "candidates": 1}}}},
        }
        completed = CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                with self.assertRaises(CLIError):
                    runner.run("prompt")

    def test_gemini_error_payload_raises(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        completed = CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"error": {"message": "bad"}}), stderr=""
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                with self.assertRaises(CLIError):
                    runner.run("prompt")

    def test_gemini_auth_failure_raises(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        completed = CompletedProcess(args=[], returncode=1, stdout="", stderr="API key not valid")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                with self.assertRaises(AuthenticationError):
                    runner.run("prompt")

    def test_gemini_timeout_raises(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", timeout_s=1, cli_version="0.65.0")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch(
                "harness.core.cli_runner.subprocess.run",
                side_effect=TimeoutExpired(cmd="gemini", timeout=1),
            ):
                with self.assertRaises(TimeoutError):
                    runner.run("prompt")

    def test_stop_on_limit_saves_and_raises_without_waiting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sentinel = Path(tmpdir) / "PAUSED"
            runner = CLIRunner(
                "gemini",
                "gemini-3.1-pro-preview",
                cli_version="0.65.0",
                paused_sentinel_path=str(sentinel),
                stop_on_limit=True,
            )
            failed = CompletedProcess(args=[], returncode=1, stdout="", stderr="RESOURCE_EXHAUSTED")

            with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
                with mock.patch("harness.core.cli_runner.subprocess.run", return_value=failed):
                    with mock.patch("harness.core.cli_runner.time.sleep") as sleep_mock:
                        with self.assertRaises(UsageLimitError):
                            runner.run("prompt", task_id="t1", condition_id="c1", turn="writer")

            sleep_mock.assert_not_called()
            self.assertEqual("t1", json.loads(sentinel.read_text())["last_task_id"])

    def test_codex_chatgpt_model_rejection_is_unsupported(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        completed = CompletedProcess(
            args=[],
            returncode=1,
            stdout='{"message":"The model is not supported when using Codex with a ChatGPT account.","code":"model_not_found"}',
            stderr="",
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="codex"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                with self.assertRaises(UnsupportedModelError):
                    runner.run("prompt")

    def test_gemini_json_output_is_parsed(self):
        payload = {
            "response": "OK",
            "stats": {
                "models": {
                    "gemini-3.8-flash": {
                        "tokens": {
                            "input": 2039,
                            "prompt": 11796,
                            "candidates": 1,
                            "cached": 9757,
                            "thoughts": 19,
                        }
                    },
                    "gemini-3.1-flash-lite": {
                        "tokens": {"prompt": 100, "candidates": 5, "cached": 40, "thoughts": 0}
                    },
                }
            },
        }
        runner = CLIRunner("gemini", "gemini-3.8-flash", cli_version="0.65.0")
        completed = CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed):
                result = runner.run("Reply exactly with OK")

        self.assertEqual("OK", result.response_text)
        self.assertEqual(2039 + 60, result.input_tokens)
        self.assertEqual(9757 + 40, result.cached_input_tokens)
        self.assertEqual(1 + 19 + 5, result.output_tokens)
        self.assertIsNone(result.cost_usd)

    def test_gemini_success_with_logged_internal_retry_does_not_wait(self):
        runner = CLIRunner("gemini", "gemini-3.8-flash", cli_version="0.65.0")
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"response": "OK", "stats": {"models": {}}}),
            stderr="Attempt 1 failed with status 503. Please try again later.",
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed) as run_mock:
                with mock.patch("harness.core.cli_runner.time.sleep") as sleep_mock:
                    result = runner.run("prompt")

        self.assertEqual("OK", result.response_text)
        self.assertEqual(1, run_mock.call_count)
        sleep_mock.assert_not_called()

    def test_gemini_failed_rate_limit_waits_and_retries(self):
        runner = CLIRunner("gemini", "gemini-3.8-flash", cli_version="0.65.0")
        failed = CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="503 This model is currently experiencing high demand. Please try again later.",
        )
        success = CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"response": "OK", "stats": {"models": {}}}),
            stderr="",
        )

        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", side_effect=[failed, success]):
                with mock.patch("harness.core.cli_runner.time.sleep", return_value=None) as sleep_mock:
                    result = runner.run("prompt")

        self.assertEqual("OK", result.response_text)
        self.assertEqual([mock.call(60)], sleep_mock.call_args_list)

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
