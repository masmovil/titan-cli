"""
Headless adapter for Antigravity CLI (agy).

Uses `agy --print <prompt>` for non-interactive execution, with
`--output-format json --json-schema` when a structured response is required.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .base import HeadlessResponse, SupportedCLI, resolve_cli_executable

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

_HEADLESS_PREAMBLE = (
    "Headless session constraints: shell commands, terminal tools, and file edits are "
    "unavailable here — any attempt is silently denied and ends the run without an "
    "answer. Do not run git or any other command. Work only with file reading, "
    "directory listing, and code search tools, and always finish by writing the final "
    "answer to the request.\n\n"
)
"""Prepended to every prompt because agy cannot be told which tools its session lacks.

Unlike Claude's --disallowedTools there is no flag that removes tools from the model's
view, so the model plans command runs, gets auto-denied, and terminates with narration
but no answer (observed live: review batches ended exactly at "I will run git status").
Telling it up front is the only available lever.
"""

_READ_ONLY_PERMISSIONS = ["read_file(*)"]
"""Allow-rules provisioned into agy's settings so headless runs can read the repo.

One rule covers all read-shaped work: agy gates listing, code search, and file
reads behind the single "read_file" permission (verified live — with only this
rule, list/search/read tools all run), and it prunes rule names it does not
recognize from the file on exit, so provisioning anything else would just be
re-added and re-pruned on every run. Read-only on purpose: write and command
tools stay unlisted, so agy keeps auto-denying them (or containing them to its
scratch sandbox) while unattended.
"""


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
        return resolve_cli_executable("agy") is not None

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
        self._ensure_read_permissions()
        executable = resolve_cli_executable("agy")
        if executable is None:
            return HeadlessResponse(stdout="", stderr="agy command not found", exit_code=127)
        cmd = [executable]
        if json_schema is not None:
            cmd += ["--output-format", "json", "--json-schema", json.dumps(json_schema)]
        if effort is not None:
            cmd += ["--effort", effort]
        if model is not None:
            cmd += ["--model", model]
        # --print consumes the very next argv token as its prompt, so any flag
        # placed after it would be swallowed as the prompt. It must come last,
        # immediately followed by the real prompt.
        cmd += ["--print", _HEADLESS_PREAMBLE + prompt]
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

    def _ensure_read_permissions(self) -> None:
        """Provision read-only allow-rules into agy's settings before each run.

        Headless agy auto-denies any tool that would need an interactive permission
        prompt — read_file included, and reading the repo is the reason a CLI is worth
        routing to at all. Its only unattended-safe switch is `permissions.allow` in its
        settings file (the alternative, --dangerously-skip-permissions, would also
        approve shell and writes). Idempotent: existing rules and unrelated settings are
        preserved, and nothing is written when the rules are already there. Best-effort:
        an unreadable or malformed file is left alone — the run then surfaces agy's own
        permission-denial message instead of this method guessing at repairs.
        """
        try:
            settings: dict[str, Any] = {}
            if _SETTINGS_PATH.exists():
                loaded = json.loads(_SETTINGS_PATH.read_text())
                if not isinstance(loaded, dict):
                    return
                settings = loaded

            permissions = settings.get("permissions")
            if not isinstance(permissions, dict):
                permissions = {}
                settings["permissions"] = permissions
            allow = permissions.get("allow")
            if not isinstance(allow, list):
                allow = []
                permissions["allow"] = allow

            missing = [rule for rule in _READ_ONLY_PERMISSIONS if rule not in allow]
            if not missing:
                return

            allow.extend(missing)
            _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return

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
            # The envelope's `response` may be empty on hard failures (e.g. quota
            # exhaustion), where the cause lives in an error-ish field instead. Surface
            # whatever the envelope carries before falling back to a generic message.
            detail = (
                envelope.get("error")
                or envelope.get("error_message")
                or envelope.get("response")
                or stderr
                or f"Antigravity CLI reported an error (status: {envelope.get('status')})"
            )
            return HeadlessResponse(
                stdout="",
                stderr=str(detail),
                exit_code=result.returncode or 1,
            )

        structured_output = envelope.get("structured_output")
        if structured_output is None:
            return HeadlessResponse(stdout=str(envelope.get("response", "")), stderr=stderr, exit_code=result.returncode)
        return HeadlessResponse(stdout=json.dumps(structured_output), stderr=stderr, exit_code=result.returncode)

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()
