"""
Tests for external_cli.adapters — HeadlessCliAdapter implementations and registry.
"""

import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from titan_cli.external_cli.adapters.base import HeadlessResponse, SupportedCLI
from titan_cli.external_cli.adapters.claude import ClaudeHeadlessAdapter
from titan_cli.external_cli.adapters.codex import CodexHeadlessAdapter
from titan_cli.external_cli.adapters.gemini import GeminiHeadlessAdapter
from titan_cli.external_cli.adapters.registry import (
    HEADLESS_ADAPTER_REGISTRY,
    get_headless_adapter,
)


# ── SupportedCLI ─────────────────────────────────────────────────────────────

class TestSupportedCLI(unittest.TestCase):

    def test_values_match_cli_commands(self):
        self.assertEqual(SupportedCLI.CLAUDE, "claude")
        self.assertEqual(SupportedCLI.GEMINI, "gemini")

    def test_is_str_compatible(self):
        self.assertIsInstance(SupportedCLI.CLAUDE, str)


# ── HeadlessResponse ─────────────────────────────────────────────────────────

class TestHeadlessResponse(unittest.TestCase):

    def test_succeeded_when_exit_code_zero(self):
        r = HeadlessResponse(stdout="ok", stderr="", exit_code=0)
        self.assertTrue(r.succeeded)

    def test_failed_when_exit_code_nonzero(self):
        r = HeadlessResponse(stdout="", stderr="err", exit_code=1)
        self.assertFalse(r.succeeded)


# ── ClaudeHeadlessAdapter ─────────────────────────────────────────────────────

class TestClaudeHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = ClaudeHeadlessAdapter()

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.CLAUDE)

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("shutil.which", return_value=None)
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

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_execute_cli_not_found(self, _):
        response = self.adapter.execute("prompt")
        self.assertEqual(response.exit_code, 127)
        self.assertIn("not found", response.stderr)

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


# ── GeminiHeadlessAdapter ─────────────────────────────────────────────────────

class TestGeminiHeadlessAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = GeminiHeadlessAdapter()

    def test_cli_name(self):
        self.assertEqual(self.adapter.cli_name, SupportedCLI.GEMINI)

    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_is_available_true(self, _):
        self.assertTrue(self.adapter.is_available())

    @patch("shutil.which", return_value=None)
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


# ── Registry ──────────────────────────────────────────────────────────────────

class TestHeadlessAdapterRegistry(unittest.TestCase):

    def test_registry_has_claude_and_gemini(self):
        self.assertIn(SupportedCLI.CLAUDE, HEADLESS_ADAPTER_REGISTRY)
        self.assertIn(SupportedCLI.GEMINI, HEADLESS_ADAPTER_REGISTRY)

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
