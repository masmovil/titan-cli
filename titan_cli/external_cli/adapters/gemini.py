"""
Headless adapter for Gemini CLI (gemini).

Uses Gemini's prompt flag in one-shot mode (`--prompt`) so Titan can run
Gemini without opening an interactive session.
"""

import re
import shutil
import subprocess
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class GeminiHeadlessAdapter:
    """
    Runs Gemini CLI in headless mode.

    Uses `--prompt <prompt>` to avoid interactive prompt mode (`-i` /
    `--prompt-interactive`), which fails when stdin is not a TTY.
    """

    @property
    def cli_name(self) -> SupportedCLI:
        return SupportedCLI.GEMINI

    @property
    def supports_structured_output(self) -> bool:
        return False

    @property
    def supports_tool_restriction(self) -> bool:
        return False

    @property
    def supports_effort_control(self) -> bool:
        return False

    @property
    def supports_model_selection(self) -> bool:
        return True

    def is_available(self) -> bool:
        return shutil.which("gemini") is not None

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
        cmd = ["gemini", "--prompt", prompt]
        if model is not None:
            cmd += ["-m", model]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            return HeadlessResponse(
                stdout=self._sanitize(result.stdout),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return HeadlessResponse(
                stdout="",
                stderr=f"Gemini CLI timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return HeadlessResponse(
                stdout="",
                stderr="gemini command not found",
                exit_code=127,
            )

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()
