"""HTTP 402 / out-of-credits must stop the run: no retry, no wait, no saved record."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from harness.core.cli_runner import CLIRunner, OutOfCreditsError, UsageLimitError
from harness.core.parser import ParseResult  # noqa: F401  (pipeline import check)
from harness.core.pipeline import BenchmarkTask, TwoPassPipeline
from harness.core.tracker import CostTracker


class OutOfCreditsTest(unittest.TestCase):
    def assert_hard_stop(self, runner, completed):
        with mock.patch.object(runner, "_resolve_executable", return_value=runner.cli):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=completed) as run_mock:
                with mock.patch("harness.core.cli_runner.time.sleep") as sleep_mock:
                    with self.assertRaises(OutOfCreditsError):
                        runner.run("prompt", task_id="t1", condition_id="c1", turn="reviewer")
        self.assertEqual(1, run_mock.call_count, "must not retry")
        sleep_mock.assert_not_called()

    def test_codex_insufficient_quota_is_hard_stop_not_rate_limit(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        event = {"type": "error", "message": "429 You exceeded your current quota, please check your plan and billing details. code: insufficient_quota"}
        self.assert_hard_stop(runner, CompletedProcess([], 1, json.dumps(event), ""))

    def test_codex_error_event_with_exit_zero(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        event = {"type": "turn.failed", "error": {"message": "insufficient_quota"}}
        self.assert_hard_stop(runner, CompletedProcess([], 0, json.dumps(event), ""))

    def test_http_402_payment_required(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        self.assert_hard_stop(runner, CompletedProcess([], 1, "", "[API Error: 402 Payment Required]"))

    def test_gemini_prepayment_depleted(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        stderr = "429 RESOURCE_EXHAUSTED Your prepayment credits are depleted. Please go to AI Studio to manage billing."
        self.assert_hard_stop(runner, CompletedProcess([], 1, "", stderr))

    def test_gemini_error_payload_with_exit_zero(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        payload = {"error": {"code": 402, "message": "Payment required"}}
        self.assert_hard_stop(runner, CompletedProcess([], 0, json.dumps(payload), ""))

    def test_claude_credit_balance_too_low(self):
        runner = CLIRunner("claude", "claude-opus-4-7", cli_version="2.0")
        payload = {"is_error": True, "result": "Credit balance is too low"}
        self.assert_hard_stop(runner, CompletedProcess([], 1, json.dumps(payload), ""))

    def test_writes_sentinel_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / "PAUSED"
            runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0", paused_sentinel_path=str(sentinel))
            self.assert_hard_stop(runner, CompletedProcess([], 1, "", "insufficient_quota"))
            self.assertEqual("out_of_credits", json.loads(sentinel.read_text())["reason"])

    def test_gemini_per_minute_quota_still_waits_and_retries(self):
        runner = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        limited = CompletedProcess([], 1, "", "429 You exceeded your current quota, please check your plan and billing details.")
        ok = CompletedProcess([], 0, json.dumps({"response": "OK", "stats": {"models": {}}}), "")
        with mock.patch.object(runner, "_resolve_executable", return_value="gemini"):
            with mock.patch("harness.core.cli_runner.subprocess.run", side_effect=[limited, ok]):
                with mock.patch("harness.core.cli_runner.time.sleep") as sleep_mock:
                    self.assertEqual("OK", runner.run("prompt").response_text)
        sleep_mock.assert_called_once()

    def test_successful_reply_mentioning_402_is_not_a_stop(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        ok = CompletedProcess([], 0, '{"usage":{"input_tokens":4021}} status code 402 payment required', "")
        with mock.patch.object(runner, "_resolve_executable", return_value="codex"):
            with mock.patch("harness.core.cli_runner.subprocess.run", return_value=ok):
                with mock.patch.object(runner, "_parse_codex_response", return_value="parsed"):
                    self.assertEqual("parsed", runner.run("prompt"))

    def test_is_a_usage_limit_error_for_existing_handlers(self):
        self.assertTrue(issubclass(OutOfCreditsError, UsageLimitError))

    def test_pipeline_propagates_and_saves_nothing(self):
        writer = CLIRunner("gemini", "gemini-3.1-pro-preview", cli_version="0.65.0")
        tracker = CostTracker()
        pipeline = TwoPassPipeline(writer, None, tracker, "B3_gemini_solo")
        task = BenchmarkTask("t1", "livecodebench", "prompt", "", {})
        failed = CompletedProcess([], 1, "", "402 Payment Required")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tracker, "save") as save_mock:
            with mock.patch.object(writer, "_resolve_executable", return_value="gemini"):
                with mock.patch("harness.core.cli_runner.subprocess.run", return_value=failed) as run_mock:
                    with self.assertRaises(OutOfCreditsError):
                        pipeline.run_task(task)
            self.assertEqual(1, run_mock.call_count, "pipeline must not retry the task")
            save_mock.assert_not_called()
            self.assertEqual([], list(Path(tmp).iterdir()))


if __name__ == "__main__":
    unittest.main()


class IsolatedCodexHomeTest(unittest.TestCase):
    def test_codex_home_sets_env_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "auth.json").write_text("{}")
            runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0", codex_home=tmp)
            self.assertEqual(tmp, runner._subprocess_env()["CODEX_HOME"])
            stdout = '{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}'
            res = runner._parse_codex_response(stdout, "", 0, 1.0, "", "", "/nonexistent")
            self.assertEqual("isolated", res.runtime_settings["codex_home"])
            self.assertEqual(0, res.runtime_settings["tool_calls"])

    def test_codex_home_without_login_is_an_auth_error(self):
        from harness.core.cli_runner import AuthenticationError
        with tempfile.TemporaryDirectory() as tmp:
            runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0", codex_home=tmp)
            with self.assertRaises(AuthenticationError):
                runner._subprocess_env()

    def test_codex_tool_events_are_counted(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        stdout = "\n".join([
            '{"type":"item.completed","item":{"type":"command_execution","command":"python3 x.py"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
        ])
        res = runner._parse_codex_response(stdout, "", 0, 1.0, "", "", "/nonexistent")
        self.assertEqual(1, res.runtime_settings["tool_calls"])
        self.assertEqual("user_default", res.runtime_settings["codex_home"])


class CodexCachedTokensTest(unittest.TestCase):
    def test_input_tokens_exclude_cached(self):
        runner = CLIRunner("codex", "gpt-5.5", cli_version="codex 1.0")
        stdout = "\n".join([
            '{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}',
            '{"type":"turn.completed","usage":{"input_tokens":12071,"cached_input_tokens":9728,"output_tokens":767}}',
        ])
        res = runner._parse_codex_response(stdout, "", 0, 1.0, "", "", "/nonexistent")
        self.assertEqual(12071 - 9728, res.input_tokens)
        self.assertEqual(9728, res.cached_input_tokens)
        self.assertTrue(res.runtime_settings["input_tokens_exclude_cached"])
