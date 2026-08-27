"""
Headless adapter for OpenCode CLI (opencode).

Uses `opencode run --format json <prompt>` for non-interactive execution.
Parses JSONL event output to extract the agent's response.
"""

import json
import re
import shutil
import subprocess
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class OpenCodeHeadlessAdapter:
    """
    Runs OpenCode CLI in headless mode via `opencode run --format json <prompt>`.

    `run` executes a single message without opening the TUI; `--format json`
    switches the output to machine-readable JSONL events, one per line.
    """

    @property
    def cli_name(self) -> SupportedCLI:
        return SupportedCLI.OPENCODE

    @property
    def supports_structured_output(self) -> bool:
        return False

    @property
    def supports_tool_restriction(self) -> bool:
        return False

    @property
    def supports_effort_control(self) -> bool:
        # OpenCode's closest knob is `--variant`, but its accepted values are
        # provider-specific (e.g. "minimal"/"high"/"max") and don't line up with
        # the low/medium/high tiers Titan passes, so it isn't wired through.
        return False

    @property
    def supports_model_selection(self) -> bool:
        return True

    def is_available(self) -> bool:
        return shutil.which("opencode") is not None

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
        cmd = ["opencode", "run", "--format", "json"]
        if model is not None:
            # OpenCode expects "provider/model" (e.g. "anthropic/claude-sonnet-4-5").
            cmd += ["-m", model]
        cmd.append(prompt)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            return HeadlessResponse(
                stdout=self._parse_json_output(result.stdout),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return HeadlessResponse(
                stdout="",
                stderr=f"OpenCode CLI timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return HeadlessResponse(
                stdout="",
                stderr="opencode command not found",
                exit_code=127,
            )

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()

    def _parse_json_output(self, jsonl_output: str) -> str:
        """
        Parse JSONL output from `opencode run --format json`.

        Each line is an event; the assistant's answer arrives as "text" events
        whose payload sits under `part.text`. Other event types (step_start,
        step_finish, tool events) carry no response text and are skipped.
        """
        if not jsonl_output or not jsonl_output.strip():
            return ""

        text_parts = []
        for line in jsonl_output.strip().split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                if text:
                    text_parts.append(text)

        return "\n".join(text_parts).strip()
