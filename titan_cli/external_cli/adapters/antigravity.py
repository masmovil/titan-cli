"""
Headless adapter for Antigravity CLI (agy).

Uses `agy --print <prompt>` for non-interactive execution, with
`--output-format json --json-schema` when a structured response is required.
"""

import json
import re
import shutil
import subprocess
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class AntigravityHeadlessAdapter:
    """
    Runs Antigravity CLI in headless mode via `agy [flags] --print <prompt>`.

    `--print` runs a single prompt non-interactively and writes the response
    to stdout. With `--output-format json --json-schema <schema>`, agy returns
    a JSON envelope whose `structured_output` field is the schema-validated
    answer.
    """

    @property
    def cli_name(self) -> SupportedCLI:
        return SupportedCLI.ANTIGRAVITY

    @property
    def supports_structured_output(self) -> bool:
        return True

    @property
    def supports_tool_restriction(self) -> bool:
        # agy has no per-invocation tool denylist flag. Headless runs are
        # still contained: tools needing a permission it cannot prompt for
        # are auto-denied unless allowed in its own settings.
        return False

    @property
    def supports_effort_control(self) -> bool:
        return True

    @property
    def supports_model_selection(self) -> bool:
        return True

    def is_available(self) -> bool:
        return shutil.which("agy") is not None

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
        cmd = ["agy"]
        if json_schema is not None:
            cmd += ["--output-format", "json", "--json-schema", json.dumps(json_schema)]
        if effort is not None:
            cmd += ["--effort", effort]
        if model is not None:
            cmd += ["--model", model]
        # --print consumes the very next argv token as its prompt, so any flag
        # placed after it would be swallowed as the prompt. It must come last,
        # immediately followed by the real prompt.
        cmd += ["--print", prompt]
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
                stderr=f"Antigravity CLI timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return HeadlessResponse(
                stdout="",
                stderr="agy command not found",
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

        On success the schema-validated answer is under `structured_output`; this
        becomes stdout as compact JSON so downstream parsing sees no surrounding
        prose. Falls back to the envelope's `response` text if no structured
        output was produced.
        """
        stderr = result.stderr.strip()
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError:
            return HeadlessResponse(stdout=self._sanitize(result.stdout), stderr=stderr, exit_code=result.returncode)

        if not isinstance(envelope, dict):
            return HeadlessResponse(stdout=self._sanitize(result.stdout), stderr=stderr, exit_code=result.returncode)

        if envelope.get("status") not in (None, "SUCCESS"):
            return HeadlessResponse(
                stdout="",
                stderr=str(envelope.get("response") or stderr or "Antigravity CLI reported an error"),
                exit_code=result.returncode or 1,
            )

        structured_output = envelope.get("structured_output")
        if structured_output is None:
            return HeadlessResponse(stdout=str(envelope.get("response", "")), stderr=stderr, exit_code=result.returncode)
        return HeadlessResponse(stdout=json.dumps(structured_output), stderr=stderr, exit_code=result.returncode)

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()
