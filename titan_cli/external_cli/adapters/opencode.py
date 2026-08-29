"""
Headless adapter for OpenCode CLI (opencode).

Uses `opencode run --format json <prompt>` for non-interactive execution.
Parses JSONL event output to extract the agent's response.
"""

import json
import os
import re
import subprocess
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI, resolve_cli_executable

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

_HEADLESS_PERMISSIONS = {
    "edit": "deny",
    "bash": {
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
        "git show*": "allow",
        "git branch*": "allow",
        "*": "deny",
    },
}
"""Per-process permission override exported as OPENCODE_PERMISSION on every run.

Headless opencode auto-rejects any tool call its config maps to "ask" (it cannot
prompt without a TTY), and a rejection ends the run mid-plan with no answer —
observed live: a PR-description run died on `git log` and produced zero output.
The env var scopes the fix to Titan's own subprocess: the user's opencode.json
is never touched (it may be JSONC with comments, which a rewrite would destroy),
and interactive opencode sessions keep their own rules. Read-shaped git commands
are the whole reason Titan routes repo tasks to a CLI, so they are allowed;
edits and every other command stay denied while unattended. File reading and
code search tools are allowed by opencode's own defaults.
"""

_HEADLESS_PREAMBLE = (
    "Headless session constraints: file edits and shell commands are unavailable "
    "here, except read-only git commands (git status / diff / log / show / branch) "
    "— any other command is denied and would end the run without an answer. Work "
    "with file reading, code search, and those git commands only, and always finish "
    "by writing the final answer to the request.\n\n"
)
"""Prepended to every prompt so the model plans around the denied tools.

A denied tool call is only reported to the model after it commits to that plan,
and an unattended run has no user to re-approve — telling it the boundaries up
front is what keeps it answering instead of stalling on a rejection.
"""


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
        return resolve_cli_executable("opencode") is not None

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
        executable = resolve_cli_executable("opencode")
        if executable is None:
            return HeadlessResponse(stdout="", stderr="opencode command not found", exit_code=127)
        cmd = [executable, "run", "--format", "json"]
        if model is not None:
            # OpenCode expects "provider/model" (e.g. "anthropic/claude-sonnet-4-5").
            cmd += ["-m", model]
        cmd.append(_HEADLESS_PREAMBLE + prompt)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                env={**os.environ, "OPENCODE_PERMISSION": json.dumps(_HEADLESS_PERMISSIONS)},
                # opencode draws a status bar by writing to /dev/tty directly,
                # bypassing the captured pipes and corrupting Titan's own TUI.
                # A new session has no controlling terminal, so that open fails
                # and opencode runs truly headless.
                stdin=subprocess.DEVNULL,
                start_new_session=True,
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

        Each line is an event; the assistant's answer arrives as "text" events whose
        payload sits under `part.text`. In agentic runs the model also narrates between
        tool calls ("Reviewing the repo state...") as ordinary "text" events, so joining
        every one of them would prepend narration to the answer. Two rules separate them:
        text parts some providers tag with phase "final_answer" win outright; otherwise
        each "tool_use" event discards the texts before it, since narration precedes tool
        work and the answer comes after the last tool.
        """
        if not jsonl_output or not jsonl_output.strip():
            return ""

        final_texts = []
        post_tool_texts = []
        all_texts = []
        for line in jsonl_output.strip().split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type == "tool_use":
                post_tool_texts.clear()
                continue
            if event_type != "text":
                continue

            part = event.get("part", {})
            text = part.get("text", "")
            if not text:
                continue
            post_tool_texts.append(text)
            all_texts.append(text)

            phase = part.get("metadata", {}).get("openai", {}).get("phase")
            if phase == "final_answer":
                final_texts.append(text)

        # A run that dies on a tool call (denied permission, tool error) ends with
        # a tool_use and leaves post_tool_texts empty. The narration before it is
        # not the answer, but it beats returning nothing: the caller's contract
        # check gets real content to reject and the user sees what the model was
        # doing when the run stopped.
        return "\n".join(final_texts or post_tool_texts or all_texts[-1:]).strip()
