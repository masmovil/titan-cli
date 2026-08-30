"""
Tests for external_cli.adapters — HeadlessCliAdapter implementations and registry.
"""

import json
import io
import inspect
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from titan_cli.external_cli.adapters.antigravity import (
    _HEADLESS_PREAMBLE,
    AntigravityHeadlessAdapter,
)
from titan_cli.external_cli.adapters.base import (
    ExternalCLIActivityPhase,
    HeadlessResponse,
    SupportedCLI,
    resolve_cli_executable,
)
from titan_cli.external_cli.adapters.claude import ClaudeHeadlessAdapter
from titan_cli.external_cli.adapters.codex import CodexHeadlessAdapter
from titan_cli.external_cli.adapters.gemini import GeminiHeadlessAdapter
from titan_cli.external_cli.adapters.opencode import (
    _HEADLESS_PERMISSIONS,
    _HEADLESS_PREAMBLE as _OPENCODE_PREAMBLE,
    OpenCodeHeadlessAdapter,
)
from titan_cli.external_cli.adapters.registry import (
    HEADLESS_ADAPTER_REGISTRY,
    get_headless_adapter,
)
from titan_cli.core.interrupt import WorkflowAborted


# ── SupportedCLI ─────────────────────────────────────────────────────────────

class TestSupportedCLI(unittest.TestCase):

    def test_values_match_cli_commands(self):
        self.assertEqual(SupportedCLI.CLAUDE, "claude")
        self.assertEqual(SupportedCLI.GEMINI, "gemini")
        self.assertEqual(SupportedCLI.OPENCODE, "opencode")
        self.assertEqual(SupportedCLI.ANTIGRAVITY, "agy")

    def test_is_str_compatible(self):
        self.assertIsInstance(SupportedCLI.CLAUDE, str)

    def test_every_registered_adapter_supports_observability_and_cancellation(self):
        required = {"on_activity", "is_cancelled"}
        for cli_name, adapter_type in HEADLESS_ADAPTER_REGISTRY.items():
            with self.subTest(cli=cli_name):
                parameters = set(inspect.signature(adapter_type.execute).parameters)
                self.assertTrue(
                    required.issubset(parameters),
                    f"{adapter_type.__name__}.execute must preserve {sorted(required)}",
                )


# ── HeadlessResponse ─────────────────────────────────────────────────────────

class TestHeadlessResponse(unittest.TestCase):

    def test_succeeded_when_exit_code_zero(self):
        r = HeadlessResponse(stdout="ok", stderr="", exit_code=0)
        self.assertTrue(r.succeeded)

    def test_failed_when_exit_code_nonzero(self):
        r = HeadlessResponse(stdout="", stderr="err", exit_code=1)
        self.assertFalse(r.succeeded)

    def test_quota_exhausted_matches_known_provider_signatures(self):
        signatures = [
            # Google (gemini / agy)
            "RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 166h",
            "Quota exceeded for quota metric 'Generate requests'",
            # OpenAI (codex)
            "You exceeded your current quota, please check your plan (insufficient_quota)",
            # Anthropic (claude)
            "Claude usage limit reached|1756290000",
        ]
        for text in signatures:
            with self.subTest(text=text):
                r = HeadlessResponse(stdout="", stderr=text, exit_code=1)
                self.assertTrue(r.quota_exhausted)

    def test_quota_exhausted_checks_stdout_too(self):
        r = HeadlessResponse(stdout="usage limit reached", stderr="", exit_code=1)
        self.assertTrue(r.quota_exhausted)

    def test_quota_exhausted_false_on_success_even_if_text_mentions_quota(self):
        r = HeadlessResponse(stdout="Your quota was exceeded last week", stderr="", exit_code=0)
        self.assertFalse(r.quota_exhausted)

    def test_quota_exhausted_false_on_unrelated_failure(self):
        r = HeadlessResponse(stdout="", stderr="model overloaded", exit_code=1)
        self.assertFalse(r.quota_exhausted)


# ── ClaudeHeadlessAdapter ─────────────────────────────────────────────────────

class TestClaudeHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = ClaudeHeadlessAdapter()
        resolver = patch("titan_cli.external_cli.adapters.claude.resolve_cli_executable", return_value="claude")
        resolver.start()
        self.addCleanup(resolver.stop)

    @patch.dict(os.environ, {"TITAN_CLAUDE_PATH": "/usr/local/bin/claude"})
    @patch("titan_cli.external_cli.adapters.base.Path.is_file", return_value=True)
    @patch("titan_cli.external_cli.adapters.base.os.access", return_value=True)
    def test_configured_cli_path_is_preferred(self, _access, _is_file):
        self.assertEqual(resolve_cli_executable("claude"), "/usr/local/bin/claude")

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.CLAUDE)

    @patch("titan_cli.external_cli.adapters.claude.resolve_cli_executable", return_value="/usr/bin/claude")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("titan_cli.external_cli.adapters.claude.resolve_cli_executable", return_value=None)
    def test_is_available_false(self, _):
        self.assertFalse(self.adapter.is_available())

    @patch("subprocess.run")
    def test_execute_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Analysis complete\n",
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("review this", cwd="/tmp", timeout=30)

        mock_run.assert_called_once_with(
            ["claude", "--print", "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=30,
        )
        self.assertEqual(response.stdout, "Analysis complete")
        self.assertEqual(response.exit_code, 0)
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_failure_exit_code(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="error", returncode=1)
        response = self.adapter.execute("prompt")
        self.assertFalse(response.succeeded)
        self.assertEqual(response.exit_code, 1)

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60))
    def test_execute_timeout(self, _):
        response = self.adapter.execute("prompt", timeout=60)
        self.assertEqual(response.exit_code, 124)
        self.assertIn("timed out", response.stderr)

    @patch("subprocess.run", side_effect=FileNotFoundError(2, "No such file", "/usr/bin/claude"))
    def test_execute_cli_not_found(self, _):
        response = self.adapter.execute("prompt")
        self.assertEqual(response.exit_code, 127)
        self.assertIn("executable not found: claude", response.stderr)

    @patch("subprocess.run", side_effect=FileNotFoundError(2, "No such file", "/missing/worktree"))
    def test_execute_reports_missing_working_directory(self, _):
        response = self.adapter.execute("prompt", cwd="/missing/worktree")
        self.assertEqual(response.exit_code, 127)
        self.assertIn("working directory not found: /missing/worktree", response.stderr)

    @patch("subprocess.run")
    def test_execute_strips_ansi_codes(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="\x1b[32mGreen text\x1b[0m\n",
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt")
        self.assertEqual(response.stdout, "Green text")

    def test_supports_structured_output(self):
        self.assertTrue(self.adapter.supports_structured_output)

    @patch("subprocess.run")
    def test_execute_with_json_schema_adds_output_format_flags(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"structured_output": {"findings": []}}),
            stderr="",
            returncode=0,
        )
        schema = {"type": "object", "properties": {"findings": {"type": "array"}}}
        self.adapter.execute("review this", cwd="/tmp", timeout=45, json_schema=schema)

        mock_run.assert_called_once_with(
            ["claude", "--print", "--output-format", "json", "--json-schema", json.dumps(schema), "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=45,
        )

    @patch("subprocess.run")
    def test_execute_with_json_schema_unwraps_structured_output(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"structured_output": {"findings": [{"title": "Bug"}]}, "is_error": False}),
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(json.loads(response.stdout), {"findings": [{"title": "Bug"}]})
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_with_json_schema_falls_back_to_result_text_when_tool_not_called(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"result": "I won't call that tool.", "is_error": False}),
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(response.stdout, "I won't call that tool.")
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_with_json_schema_surfaces_cli_error(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"is_error": True, "result": "API Error: 400 bad schema"}),
            stderr="",
            returncode=1,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertFalse(response.succeeded)
        self.assertIn("bad schema", response.stderr)

    @patch("subprocess.run")
    def test_execute_with_json_schema_falls_back_on_unparseable_envelope(self, mock_run):
        mock_run.return_value = MagicMock(stdout="not json at all", stderr="", returncode=0)
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(response.stdout, "not json at all")
        self.assertTrue(response.succeeded)

    def test_supports_tool_restriction(self):
        self.assertTrue(self.adapter.supports_tool_restriction)

    @patch("subprocess.run")
    def test_execute_with_disallowed_tools_adds_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute(
            "review this", cwd="/tmp", timeout=45, disallowed_tools=["Bash", "Agent"]
        )

        mock_run.assert_called_once_with(
            ["claude", "--print", "--disallowedTools=Bash,Agent", "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=45,
        )

    @patch("subprocess.run")
    def test_execute_without_disallowed_tools_omits_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("review this")

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--disallowedTools", called_cmd)

    def test_supports_effort_control(self):
        self.assertTrue(self.adapter.supports_effort_control)

    @patch("subprocess.run")
    def test_execute_with_effort_adds_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("review this", cwd="/tmp", timeout=45, effort="medium")

        mock_run.assert_called_once_with(
            ["claude", "--print", "--effort", "medium", "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=45,
        )

    @patch("subprocess.run")
    def test_execute_without_effort_omits_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("review this")

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--effort", called_cmd)


# ── CodexHeadlessAdapter ──────────────────────────────────────────────────────

class TestCodexHeadlessAdapterStructuredOutput(unittest.TestCase):
    """Codex has no structured-output support (yet) — json_schema must be a no-op."""

    def setUp(self):
        self.adapter = CodexHeadlessAdapter()
        resolver = patch("titan_cli.external_cli.adapters.codex.resolve_cli_executable", return_value="codex")
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_supports_structured_output_is_false(self):
        self.assertFalse(self.adapter.supports_structured_output)

    def _process(self, stdout="", stderr="", returncode=0):
        process = MagicMock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO(stdout)
        process.stderr = io.StringIO(stderr)
        process.returncode = returncode
        process.poll.return_value = returncode
        process.wait.return_value = returncode
        return process

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_sends_prompt_through_closed_dedicated_stdin(self, mock_popen):
        process = self._process()
        process.stdin = MagicMock()
        mock_popen.return_value = process

        self.adapter.execute("large review prompt", cwd="/repo")

        self.assertEqual(mock_popen.call_args.args[0][-1], "-")
        self.assertEqual(mock_popen.call_args.kwargs["stdin"], subprocess.PIPE)
        process.stdin.write.assert_called_once_with("large review prompt")
        process.stdin.close.assert_called_once_with()

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_ignores_json_schema(self, mock_popen):
        mock_popen.return_value = self._process()
        self.adapter.execute("prompt", json_schema={"type": "object"})

        called_cmd = mock_popen.call_args.args[0]
        self.assertNotIn("--json-schema", called_cmd)

    def test_supports_tool_restriction_is_false(self):
        self.assertFalse(self.adapter.supports_tool_restriction)

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_ignores_disallowed_tools(self, mock_popen):
        mock_popen.return_value = self._process()
        self.adapter.execute("prompt", disallowed_tools=["Bash", "Agent"])

        called_cmd = mock_popen.call_args.args[0]
        self.assertNotIn("--disallowedTools", called_cmd)

    def test_supports_effort_control_is_false(self):
        self.assertFalse(self.adapter.supports_effort_control)

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_ignores_effort(self, mock_popen):
        mock_popen.return_value = self._process()
        self.adapter.execute("prompt", effort="medium")

        called_cmd = mock_popen.call_args.args[0]
        self.assertNotIn("--effort", called_cmd)

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_streams_safe_activity_and_extracts_answer(self, mock_popen):
        jsonl = "\n".join([
            json.dumps({"type": "thread.started", "thread_id": "secret-thread"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "cat private.env"},
            }),
            json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final answer"},
            }),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
        ]) + "\n"
        mock_popen.return_value = self._process(stdout=jsonl)
        activities = []

        response = self.adapter.execute("prompt", on_activity=activities.append)

        self.assertEqual(response.stdout, "final answer")
        self.assertTrue(response.succeeded)
        self.assertEqual(activities[0].phase, ExternalCLIActivityPhase.STARTED)
        self.assertEqual(activities[-1].phase, ExternalCLIActivityPhase.COMPLETED)
        self.assertTrue(any(item.activity_kind == "command_execution" for item in activities))
        self.assertNotIn("cat private.env", " ".join(item.message for item in activities))

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_execute_terminates_subprocess_when_run_is_cancelled(self, mock_popen):
        process = self._process()
        process.poll.return_value = None
        mock_popen.return_value = process
        activities = []

        with self.assertRaises(WorkflowAborted):
            self.adapter.execute(
                "prompt",
                on_activity=activities.append,
                is_cancelled=lambda: True,
            )

        process.terminate.assert_called_once()
        self.assertEqual(activities[-1].phase, ExternalCLIActivityPhase.CANCELLED)

    @patch("titan_cli.external_cli.adapters.codex.subprocess.Popen")
    def test_activity_callback_failure_does_not_fail_provider_call(self, mock_popen):
        jsonl = json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "answer"},
        }) + "\n"
        mock_popen.return_value = self._process(stdout=jsonl)

        response = self.adapter.execute(
            "prompt",
            on_activity=lambda _activity: (_ for _ in ()).throw(RuntimeError("UI gone")),
        )

        self.assertTrue(response.succeeded)
        self.assertEqual(response.stdout, "answer")


# ── GeminiHeadlessAdapter ─────────────────────────────────────────────────────

class TestGeminiHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = GeminiHeadlessAdapter()
        resolver = patch("titan_cli.external_cli.adapters.gemini.resolve_cli_executable", return_value="gemini")
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.GEMINI)

    @patch("titan_cli.external_cli.adapters.gemini.resolve_cli_executable", return_value="/usr/bin/gemini")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("titan_cli.external_cli.adapters.gemini.resolve_cli_executable", return_value=None)
    def test_is_available_false(self, _):
        self.assertFalse(self.adapter.is_available())

    def test_supports_structured_output_is_false(self):
        self.assertFalse(self.adapter.supports_structured_output)

    @patch("subprocess.run")
    def test_execute_passes_prompt_with_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="response\n", stderr="", returncode=0)
        self.adapter.execute("my prompt", cwd="/repo", timeout=45)

        mock_run.assert_called_once_with(
            ["gemini", "--prompt", "my prompt"],
            capture_output=True,
            text=True,
            cwd="/repo",
            timeout=45,
        )

    @patch("subprocess.run")
    def test_execute_ignores_json_schema(self, mock_run):
        mock_run.return_value = MagicMock(stdout="response\n", stderr="", returncode=0)
        self.adapter.execute("my prompt", json_schema={"type": "object"})

        mock_run.assert_called_once_with(
            ["gemini", "--prompt", "my prompt"],
            capture_output=True,
            text=True,
            cwd=None,
            timeout=60,
        )

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gemini", timeout=60))
    def test_execute_timeout(self, _):
        response = self.adapter.execute("prompt", timeout=60)
        self.assertEqual(response.exit_code, 124)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_execute_cli_not_found(self, _):
        response = self.adapter.execute("prompt")
        self.assertEqual(response.exit_code, 127)

    def test_supports_tool_restriction_is_false(self):
        self.assertFalse(self.adapter.supports_tool_restriction)

    @patch("subprocess.run")
    def test_execute_ignores_disallowed_tools(self, mock_run):
        mock_run.return_value = MagicMock(stdout="response\n", stderr="", returncode=0)
        self.adapter.execute("my prompt", disallowed_tools=["Bash", "Agent"])

        mock_run.assert_called_once_with(
            ["gemini", "--prompt", "my prompt"],
            capture_output=True,
            text=True,
            cwd=None,
            timeout=60,
        )

    def test_supports_effort_control_is_false(self):
        self.assertFalse(self.adapter.supports_effort_control)

    @patch("subprocess.run")
    def test_execute_ignores_effort(self, mock_run):
        mock_run.return_value = MagicMock(stdout="response\n", stderr="", returncode=0)
        self.adapter.execute("my prompt", effort="medium")

        mock_run.assert_called_once_with(
            ["gemini", "--prompt", "my prompt"],
            capture_output=True,
            text=True,
            cwd=None,
            timeout=60,
        )


# ── OpenCodeHeadlessAdapter ───────────────────────────────────────────────────

class TestOpenCodeHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = OpenCodeHeadlessAdapter()
        resolver = patch("titan_cli.external_cli.adapters.opencode.resolve_cli_executable", return_value="opencode")
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.OPENCODE)

    @patch("titan_cli.external_cli.adapters.opencode.resolve_cli_executable", return_value="/usr/bin/opencode")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("titan_cli.external_cli.adapters.opencode.resolve_cli_executable", return_value=None)
    def test_is_available_false(self, _):
        self.assertFalse(self.adapter.is_available())

    @patch("subprocess.run")
    def test_execute_uses_run_with_json_format(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("my prompt", cwd="/repo", timeout=45)

        kwargs = mock_run.call_args.kwargs
        self.assertEqual(
            mock_run.call_args.args[0],
            ["opencode", "run", "--format", "json", _OPENCODE_PREAMBLE + "my prompt"],
        )
        self.assertEqual(kwargs["cwd"], "/repo")
        self.assertEqual(kwargs["timeout"], 45)
        # Detached from the controlling tty so opencode cannot draw its
        # status bar over Titan's TUI via /dev/tty.
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(kwargs["start_new_session"])

    @patch("subprocess.run")
    def test_execute_exports_readonly_permission_override(self, mock_run):
        # Headless opencode auto-rejects "ask" permissions and the run dies without
        # an answer; the env var scopes read-only git allows to Titan's subprocess
        # without touching the user's own opencode config.
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("prompt")

        env = mock_run.call_args.kwargs["env"]
        self.assertEqual(json.loads(env["OPENCODE_PERMISSION"]), _HEADLESS_PERMISSIONS)
        self.assertEqual(_HEADLESS_PERMISSIONS["edit"], "deny")
        self.assertEqual(_HEADLESS_PERMISSIONS["bash"]["*"], "deny")
        # The rest of the environment is inherited, not replaced.
        self.assertIn("PATH", env)

    @patch("subprocess.run")
    def test_execute_with_model_adds_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("prompt", model="anthropic/claude-sonnet-4-5")

        called_cmd = mock_run.call_args.args[0]
        self.assertIn("-m", called_cmd)
        self.assertIn("anthropic/claude-sonnet-4-5", called_cmd)

    @patch("subprocess.run")
    def test_execute_extracts_text_events_from_jsonl(self, mock_run):
        jsonl = "\n".join([
            json.dumps({"type": "step_start", "part": {"type": "step-start"}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "pong"}}),
            json.dumps({"type": "step_finish", "part": {"reason": "stop"}}),
        ])
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "pong")
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_joins_multiple_text_events(self, mock_run):
        jsonl = "\n".join([
            json.dumps({"type": "text", "part": {"type": "text", "text": "first"}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "second"}}),
        ])
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "first\nsecond")

    @patch("subprocess.run")
    def test_execute_skips_unparseable_lines(self, mock_run):
        jsonl = "not json\n" + json.dumps({"type": "text", "part": {"text": "ok"}})
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "ok")

    @patch("subprocess.run")
    def test_execute_discards_narration_before_tool_calls(self, mock_run):
        # Agentic runs narrate between tool calls as plain "text" events; only what
        # comes after the last tool is the answer.
        jsonl = "\n".join([
            json.dumps({"type": "text", "part": {"text": "Reviewing the repo state"}}),
            json.dumps({"type": "tool_use", "part": {"tool": "read"}}),
            json.dumps({"type": "text", "part": {"text": "Now checking the diff"}}),
            json.dumps({"type": "tool_use", "part": {"tool": "bash"}}),
            json.dumps({"type": "text", "part": {"text": "The real answer"}}),
        ])
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "The real answer")

    @patch("subprocess.run")
    def test_execute_prefers_final_answer_phase_over_narration(self, mock_run):
        # Some providers tag the answer explicitly; narration in the same step must not
        # be joined in front of it.
        jsonl = "\n".join([
            json.dumps({"type": "tool_use", "part": {"tool": "read"}}),
            json.dumps({"type": "text", "part": {"text": "Let me summarize"}}),
            json.dumps({"type": "text", "part": {
                "text": "The real answer",
                "metadata": {"openai": {"phase": "final_answer"}},
            }}),
        ])
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "The real answer")

    @patch("subprocess.run")
    def test_execute_falls_back_to_last_narration_when_run_dies_on_a_tool(self, mock_run):
        # A run that ends on a tool_use (denied permission, tool error) has no text
        # after the last tool; the last narration beats returning an empty string.
        jsonl = "\n".join([
            json.dumps({"type": "text", "part": {"text": "Reviewing the repo state"}}),
            json.dumps({"type": "tool_use", "part": {"tool": "read"}}),
            json.dumps({"type": "text", "part": {"text": "Checking the commit log"}}),
            json.dumps({"type": "tool_use", "part": {"tool": "bash", "state": {"status": "error"}}}),
        ])
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=0)
        response = self.adapter.execute("prompt")

        self.assertEqual(response.stdout, "Checking the commit log")

    @patch("subprocess.run")
    def test_execute_surfaces_json_error_when_stderr_is_empty(self, mock_run):
        jsonl = json.dumps({
            "type": "error",
            "error": {"name": "ProviderAuthError", "data": {"message": "No API key configured"}},
        })
        mock_run.return_value = MagicMock(stdout=jsonl, stderr="", returncode=1)

        response = self.adapter.execute("prompt")

        self.assertEqual(response.exit_code, 1)
        self.assertEqual(response.stderr, "No API key configured")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=60))
    def test_execute_timeout(self, _):
        response = self.adapter.execute("prompt", timeout=60)
        self.assertEqual(response.exit_code, 124)
        self.assertIn("timed out", response.stderr)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_execute_cli_not_found(self, _):
        response = self.adapter.execute("prompt")
        self.assertEqual(response.exit_code, 127)
        self.assertIn("not found", response.stderr)

    def test_supports_structured_output_is_false(self):
        self.assertFalse(self.adapter.supports_structured_output)

    @patch("subprocess.run")
    def test_execute_ignores_json_schema(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("prompt", json_schema={"type": "object"})

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--json-schema", called_cmd)

    def test_supports_tool_restriction_is_false(self):
        self.assertFalse(self.adapter.supports_tool_restriction)

    @patch("subprocess.run")
    def test_execute_ignores_disallowed_tools(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("prompt", disallowed_tools=["Bash", "Agent"])

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--disallowedTools", called_cmd)

    def test_supports_effort_control_is_false(self):
        self.assertFalse(self.adapter.supports_effort_control)

    @patch("subprocess.run")
    def test_execute_ignores_effort(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.adapter.execute("prompt", effort="medium")

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--effort", called_cmd)
        self.assertNotIn("--variant", called_cmd)


# ── AntigravityHeadlessAdapter ────────────────────────────────────────────────

class TestAntigravityHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = AntigravityHeadlessAdapter()
        resolver = patch("titan_cli.external_cli.adapters.antigravity.resolve_cli_executable", return_value="agy")
        resolver.start()
        self.addCleanup(resolver.stop)
        # execute() provisions agy's settings file; point it at a temp dir so no
        # test ever touches the real one in the user's home.
        self._settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._settings_dir.cleanup)
        self.settings_path = Path(self._settings_dir.name) / "settings.json"
        patcher = patch(
            "titan_cli.external_cli.adapters.antigravity._SETTINGS_PATH", self.settings_path
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.ANTIGRAVITY)

    @patch("titan_cli.external_cli.adapters.antigravity.resolve_cli_executable", return_value="/usr/bin/agy")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("titan_cli.external_cli.adapters.antigravity.resolve_cli_executable", return_value=None)
    def test_is_available_false(self, _):
        self.assertFalse(self.adapter.is_available())

    @patch("subprocess.run")
    def test_execute_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="pong\n", stderr="", returncode=0)
        response = self.adapter.execute("review this", cwd="/tmp", timeout=30)

        mock_run.assert_called_once_with(
            ["agy", "--print", _HEADLESS_PREAMBLE + "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=30,
        )
        self.assertEqual(response.stdout, "pong")
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_print_flag_is_last_and_immediately_precedes_prompt(self, mock_run):
        # --print consumes the next argv token as its prompt; any flag placed
        # after it would be swallowed. Every option must come before it.
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute(
            "the prompt",
            json_schema={"type": "object"},
            effort="high",
            model="gemini-3-pro",
        )

        called_cmd = mock_run.call_args.args[0]
        self.assertEqual(called_cmd[-2:], ["--print", _HEADLESS_PREAMBLE + "the prompt"])

    @patch("subprocess.run")
    def test_execute_strips_ansi_codes(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="\x1b[32mGreen text\x1b[0m\n",
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt")
        self.assertEqual(response.stdout, "Green text")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=60))
    def test_execute_timeout(self, _):
        response = self.adapter.execute("prompt", timeout=60)
        self.assertEqual(response.exit_code, 124)
        self.assertIn("timed out", response.stderr)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_execute_cli_not_found(self, _):
        response = self.adapter.execute("prompt")
        self.assertEqual(response.exit_code, 127)
        self.assertIn("not found", response.stderr)

    def test_supports_structured_output(self):
        self.assertTrue(self.adapter.supports_structured_output)

    @patch("subprocess.run")
    def test_execute_with_json_schema_adds_output_format_flags(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"status": "SUCCESS", "structured_output": {"findings": []}}),
            stderr="",
            returncode=0,
        )
        schema = {"type": "object", "properties": {"findings": {"type": "array"}}}
        self.adapter.execute("review this", cwd="/tmp", timeout=45, json_schema=schema)

        mock_run.assert_called_once_with(
            ["agy", "--output-format", "json", "--json-schema", json.dumps(schema), "--print", _HEADLESS_PREAMBLE + "review this"],
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=45,
        )

    @patch("subprocess.run")
    def test_execute_with_json_schema_unwraps_structured_output(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"status": "SUCCESS", "structured_output": {"findings": [{"title": "Bug"}]}}),
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(json.loads(response.stdout), {"findings": [{"title": "Bug"}]})
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_with_json_schema_falls_back_to_response_text(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"status": "SUCCESS", "response": "prose answer"}),
            stderr="",
            returncode=0,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(response.stdout, "prose answer")
        self.assertTrue(response.succeeded)

    @patch("subprocess.run")
    def test_execute_with_json_schema_surfaces_cli_error(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"status": "ERROR", "response": "quota exceeded"}),
            stderr="",
            returncode=1,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertFalse(response.succeeded)
        self.assertIn("quota exceeded", response.stderr)

    @patch("subprocess.run")
    def test_execute_with_json_schema_surfaces_error_field_when_response_empty(self, mock_run):
        # Hard failures (e.g. quota exhaustion) leave `response` empty and put the
        # cause in an error field — that detail must reach the user, not a generic
        # "reported an error" message.
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {"status": "FAILED", "response": "", "error": "RESOURCE_EXHAUSTED (429): Individual quota reached"}
            ),
            stderr="",
            returncode=1,
        )
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertFalse(response.succeeded)
        self.assertIn("RESOURCE_EXHAUSTED", response.stderr)

    @patch("subprocess.run")
    def test_execute_with_json_schema_falls_back_on_unparseable_envelope(self, mock_run):
        mock_run.return_value = MagicMock(stdout="not json at all", stderr="", returncode=0)
        response = self.adapter.execute("prompt", json_schema={"type": "object"})

        self.assertEqual(response.stdout, "not json at all")
        self.assertTrue(response.succeeded)

    def test_supports_tool_restriction_is_false(self):
        self.assertFalse(self.adapter.supports_tool_restriction)

    @patch("subprocess.run")
    def test_execute_ignores_disallowed_tools(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("prompt", disallowed_tools=["Bash", "Agent"])

        called_cmd = mock_run.call_args.args[0]
        self.assertNotIn("--disallowedTools", called_cmd)

    def test_supports_effort_control(self):
        self.assertTrue(self.adapter.supports_effort_control)

    @patch("subprocess.run")
    def test_execute_with_effort_adds_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("review this", effort="medium")

        called_cmd = mock_run.call_args.args[0]
        self.assertIn("--effort", called_cmd)
        self.assertIn("medium", called_cmd)

    def test_supports_model_selection(self):
        self.assertTrue(self.adapter.supports_model_selection)

    @patch("subprocess.run")
    def test_execute_with_model_adds_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("prompt", model="gemini-3-pro")

        called_cmd = mock_run.call_args.args[0]
        self.assertIn("--model", called_cmd)
        self.assertIn("gemini-3-pro", called_cmd)

    # ── read-permission provisioning ──────────────────────────────────────────

    @patch("subprocess.run")
    def test_execute_creates_settings_with_read_rules_when_absent(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.adapter.execute("prompt")

        settings = json.loads(self.settings_path.read_text())
        self.assertIn("read_file(*)", settings["permissions"]["allow"])

    @patch("subprocess.run")
    def test_execute_merges_rules_preserving_existing_settings(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.settings_path.write_text(json.dumps({
            "colorScheme": "dark",
            "permissions": {"allow": ["command(git status)"]},
        }))

        self.adapter.execute("prompt")

        settings = json.loads(self.settings_path.read_text())
        self.assertEqual(settings["colorScheme"], "dark")
        self.assertIn("command(git status)", settings["permissions"]["allow"])
        self.assertIn("read_file(*)", settings["permissions"]["allow"])

    @patch("subprocess.run")
    def test_execute_does_not_rewrite_settings_when_rules_present(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        from titan_cli.external_cli.adapters.antigravity import _READ_ONLY_PERMISSIONS

        original = json.dumps({"permissions": {"allow": list(_READ_ONLY_PERMISSIONS)}})
        self.settings_path.write_text(original)

        self.adapter.execute("prompt")

        self.assertEqual(self.settings_path.read_text(), original)

    @patch("subprocess.run")
    def test_execute_leaves_malformed_settings_alone_and_still_runs(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        self.settings_path.write_text("{not valid json")

        response = self.adapter.execute("prompt")

        self.assertEqual(self.settings_path.read_text(), "{not valid json")
        self.assertEqual(response.stdout, "ok")
        mock_run.assert_called_once()


# ── Registry ──────────────────────────────────────────────────────────────────

class TestHeadlessAdapterRegistry(unittest.TestCase):

    def test_registry_has_all_supported_clis(self):
        self.assertIn(SupportedCLI.CLAUDE, HEADLESS_ADAPTER_REGISTRY)
        self.assertIn(SupportedCLI.GEMINI, HEADLESS_ADAPTER_REGISTRY)
        self.assertIn(SupportedCLI.CODEX, HEADLESS_ADAPTER_REGISTRY)
        self.assertIn(SupportedCLI.OPENCODE, HEADLESS_ADAPTER_REGISTRY)
        self.assertIn(SupportedCLI.ANTIGRAVITY, HEADLESS_ADAPTER_REGISTRY)

    def test_get_headless_adapter_opencode(self):
        adapter = get_headless_adapter(SupportedCLI.OPENCODE)
        self.assertIsInstance(adapter, OpenCodeHeadlessAdapter)

    def test_get_headless_adapter_antigravity_plain_string(self):
        # StrEnum compatibility: "agy" == SupportedCLI.ANTIGRAVITY
        adapter = get_headless_adapter("agy")
        self.assertIsInstance(adapter, AntigravityHeadlessAdapter)

    def test_get_headless_adapter_claude(self):
        adapter = get_headless_adapter(SupportedCLI.CLAUDE)
        self.assertIsInstance(adapter, ClaudeHeadlessAdapter)

    def test_get_headless_adapter_gemini(self):
        adapter = get_headless_adapter(SupportedCLI.GEMINI)
        self.assertIsInstance(adapter, GeminiHeadlessAdapter)

    def test_get_headless_adapter_plain_string(self):
        # StrEnum compatibility: "claude" == SupportedCLI.CLAUDE
        adapter = get_headless_adapter("claude")
        self.assertIsInstance(adapter, ClaudeHeadlessAdapter)

    def test_get_headless_adapter_unknown_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_headless_adapter("unknown_cli")
        self.assertIn("unknown_cli", str(ctx.exception))

    def test_get_headless_adapter_returns_new_instance_each_call(self):
        a1 = get_headless_adapter(SupportedCLI.CLAUDE)
        a2 = get_headless_adapter(SupportedCLI.CLAUDE)
        self.assertIsNot(a1, a2)


if __name__ == "__main__":
    unittest.main()
