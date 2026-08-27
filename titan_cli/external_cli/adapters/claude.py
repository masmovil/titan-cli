"""
Headless adapter for Claude CLI (claude).

Uses `claude --print <prompt>` for non-interactive execution.
"""

import json
import re
import shutil
import subprocess
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class ClaudeHeadlessAdapter:
    """
    Runs Claude CLI in headless mode via `claude --print <prompt>`.

    The --print flag makes Claude write the response to stdout
    and exit immediately, without starting an interactive session.
    """

    @property
    def cli_name(self) -> SupportedCLI:
        return SupportedCLI.CLAUDE

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def supports_tool_restriction(self) -> bool:
        return True

    @property
    def supports_effort_control(self) -> bool:
        return True

    @property
    def supports_model_selection(self) -> bool:
        return True

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def execute(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        json_schema: Optional[dict[str, Any]] = None,
        disallowed_tools: Optional[list[str]] = None,
        effort: Optional[str] = None,
        model: Optional[str] = None,
    ) -> HeadlessResponse:
        cmd = ["claude", "--print"]
        if json_schema is not None:
            cmd += ["--output-format", "json", "--json-schema", json.dumps(json_schema)]
        if disallowed_tools:
            # --disallowedTools is a variadic flag with no natural terminator: passed as
            # separate argv tokens, it keeps consuming words until the next recognized flag,
            # swallowing the trailing prompt argument as if it were another tool name. A
            # single comma-joined token avoids that ambiguity.
            cmd += [f"--disallowedTools={','.join(disallowed_tools)}"]
        if effort is not None:
            cmd += ["--effort", effort]
        if model is not None:
            cmd += ["--model", model]
        cmd.append(prompt)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return HeadlessResponse(
                stdout="",
                stderr=f"Claude CLI timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return HeadlessResponse(
                stdout="",
                stderr="claude command not found",
                exit_code=127,
            )

        if json_schema is None:
            return HeadlessResponse(
                stdout=self._sanitize(result.stdout),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
            )
        return self._parse_structured_result(result)

    def _parse_structured_result(self, result: subprocess.CompletedProcess) -> HeadlessResponse:
        """Unwrap the `--output-format json` envelope for a structured-output call.

        On success, the model's schema-validated answer is under `structured_output`;
        this becomes stdout as compact JSON so downstream parsing sees no surrounding
        prose. Falls back to the raw envelope's `result` text if the model didn't end up
        calling the structured-output tool (e.g. it judged the request ambiguous).
        """
        stderr = result.stderr.strip()
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError:
            return HeadlessResponse(stdout=self._sanitize(result.stdout), stderr=stderr, exit_code=result.returncode)

        if not isinstance(envelope, dict):
            return HeadlessResponse(stdout=self._sanitize(result.stdout), stderr=stderr, exit_code=result.returncode)

        if envelope.get("is_error"):
            return HeadlessResponse(
                stdout="",
                stderr=str(envelope.get("result") or stderr or "Claude CLI reported an error"),
                exit_code=result.returncode or 1,
            )

        structured_output = envelope.get("structured_output")
        if structured_output is None:
            return HeadlessResponse(stdout=str(envelope.get("result", "")), stderr=stderr, exit_code=result.returncode)
        return HeadlessResponse(stdout=json.dumps(structured_output), stderr=stderr, exit_code=result.returncode)

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()
