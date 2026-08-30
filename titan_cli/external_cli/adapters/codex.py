"""
Headless adapter for Codex CLI.

Uses `codex exec --json -` with stdin for non-interactive execution.
Parses JSONL output to extract the agent's response.
"""

import json
import queue
import re
import subprocess
import threading
import time
from typing import Any, Callable, Optional

from titan_cli.core.interrupt import WorkflowAborted, abort_requested

from .base import (
    ExternalCLIActivity,
    ExternalCLIActivityCallback,
    ExternalCLIActivityPhase,
    HeadlessResponse,
    SupportedCLI,
    resolve_cli_executable,
)

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class CodexHeadlessAdapter:
    """
    Runs Codex CLI in headless mode via `codex exec --json --ephemeral <prompt>`.

    Uses flags for non-interactive execution:
    - --json: machine-readable JSONL output
    - --ephemeral: don't save session files to disk
    """

    heartbeat_interval_seconds = 10.0
    poll_interval_seconds = 0.25

    @property
    def cli_name(self) -> SupportedCLI:
        return SupportedCLI.CODEX

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
        return resolve_cli_executable("codex") is not None

    def execute(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        json_schema: Optional[dict[str, Any]] = None,
        disallowed_tools: Optional[list[str]] = None,
        effort: Optional[str] = None,
        model: Optional[str] = None,
        on_activity: Optional[ExternalCLIActivityCallback] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> HeadlessResponse:
        # Use flags for non-interactive headless execution:
        # - --json: machine-readable JSONL output
        # - --ephemeral: don't save session to disk
        executable = resolve_cli_executable("codex")
        if executable is None:
            return HeadlessResponse(stdout="", stderr="codex command not found", exit_code=127)
        cmd = [executable, "exec", "--json", "--ephemeral"]
        if model is not None:
            cmd += ["-m", model]
        cmd.append(prompt)
        started_at = time.monotonic()
        last_activity_at = started_at

        def emit(
            phase: ExternalCLIActivityPhase,
            message: str,
            *,
            activity_kind: Optional[str] = None,
            metadata: Optional[dict[str, Any]] = None,
            marks_activity: bool = False,
        ) -> None:
            nonlocal last_activity_at
            now = time.monotonic()
            if marks_activity:
                last_activity_at = now
            if on_activity is None:
                return
            try:
                on_activity(
                    ExternalCLIActivity(
                        provider=SupportedCLI.CODEX,
                        phase=phase,
                        message=message,
                        elapsed_seconds=max(0, now - started_at),
                        idle_seconds=max(0, now - last_activity_at),
                        activity_kind=activity_kind,
                        metadata=metadata,
                    )
                )
            except Exception:
                # Observability must never make the provider call fail.
                return

        emit(ExternalCLIActivityPhase.STARTED, "Codex started processing the request")
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                bufsize=1,
            )
            stdout_text, stderr_text = self._collect_stream(
                process,
                timeout=timeout,
                started_at=started_at,
                emit=emit,
                is_cancelled=is_cancelled,
            )
            emit(
                ExternalCLIActivityPhase.COMPLETED
                if process.returncode == 0
                else ExternalCLIActivityPhase.FAILED,
                "Codex finished processing the request"
                if process.returncode == 0
                else "Codex exited with an error",
            )
            return HeadlessResponse(
                stdout=self._parse_json_output(stdout_text),
                stderr=stderr_text.strip(),
                exit_code=process.returncode or 0,
            )
        except TimeoutError:
            emit(
                ExternalCLIActivityPhase.TIMED_OUT,
                f"Codex timed out after {timeout}s",
                metadata={"timeout_seconds": timeout},
            )
            return HeadlessResponse(
                stdout="",
                stderr=f"Codex CLI timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            emit(ExternalCLIActivityPhase.FAILED, "Codex executable was not found")
            return HeadlessResponse(
                stdout="",
                stderr="codex command not found",
                exit_code=127,
            )

    def _collect_stream(self, process, *, timeout, started_at, emit, is_cancelled):
        """Drain JSONL/stdout and stderr without hiding long-running activity."""
        lines: queue.Queue[tuple[str, Optional[str]]] = queue.Queue()

        def read_stream(name: str, stream) -> None:
            try:
                for line in iter(stream.readline, ""):
                    lines.put((name, line))
            finally:
                lines.put((name, None))

        readers = [
            threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        closed_streams: set[str] = set()
        last_activity_at = started_at
        next_heartbeat = started_at + self.heartbeat_interval_seconds

        while len(closed_streams) < 2:
            now = time.monotonic()
            if abort_requested() or (is_cancelled is not None and is_cancelled()):
                self._terminate(process)
                emit(ExternalCLIActivityPhase.CANCELLED, "Codex execution was cancelled")
                raise WorkflowAborted("Codex execution cancelled")
            if now - started_at >= timeout:
                self._terminate(process)
                raise TimeoutError

            wait_for = min(self.poll_interval_seconds, max(0.01, next_heartbeat - now))
            try:
                stream_name, line = lines.get(timeout=wait_for)
            except queue.Empty:
                stream_name, line = "", ""

            if line is None:
                closed_streams.add(stream_name)
            elif line:
                if stream_name == "stdout":
                    stdout_lines.append(line)
                    activity = self._activity_from_json_line(line)
                    if activity is not None:
                        phase, message, kind, metadata = activity
                        last_activity_at = time.monotonic()
                        emit(
                            phase,
                            message,
                            activity_kind=kind,
                            metadata=metadata,
                            marks_activity=True,
                        )
                else:
                    stderr_lines.append(line)

            now = time.monotonic()
            if now >= next_heartbeat:
                emit(
                    ExternalCLIActivityPhase.HEARTBEAT,
                    "Codex is still working",
                    activity_kind="heartbeat",
                    metadata={"idle_seconds": round(now - last_activity_at, 1)},
                )
                next_heartbeat = now + self.heartbeat_interval_seconds

        process.wait()
        return "".join(stdout_lines), "".join(stderr_lines)

    @staticmethod
    def _terminate(process) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @staticmethod
    def _activity_from_json_line(line: str):
        """Map Codex JSONL to safe activity without exposing model reasoning."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None

        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            return ExternalCLIActivityPhase.ACTIVITY, "Codex session connected", "session", None
        if event_type == "turn.started":
            return ExternalCLIActivityPhase.ACTIVITY, "Codex is analysing the request", "turn", None
        if event_type in {"turn.completed", "turn.failed"}:
            phase = ExternalCLIActivityPhase.ACTIVITY if event_type == "turn.completed" else ExternalCLIActivityPhase.FAILED
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else None
            return phase, "Codex completed an analysis turn" if phase == ExternalCLIActivityPhase.ACTIVITY else "Codex analysis turn failed", "turn", usage
        if event_type in {"item.started", "item.completed"}:
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            item_type = str(item.get("type") or "activity")
            messages = {
                "command_execution": "Codex is inspecting the project",
                "mcp_tool_call": "Codex is using a project tool",
                "file_change": "Codex prepared a file change",
                "web_search": "Codex is checking external information",
                "agent_message": "Codex produced a response",
                "reasoning": "Codex is reasoning about the request",
            }
            return ExternalCLIActivityPhase.ACTIVITY, messages.get(item_type, "Codex reported new activity"), item_type, None
        if event_type == "error":
            return ExternalCLIActivityPhase.FAILED, "Codex reported an execution error", "error", None
        return None

    def _sanitize(self, text: str) -> str:
        """Strip ANSI escape codes and trailing whitespace."""
        return _ANSI_ESCAPE.sub("", text).strip()

    def _parse_json_output(self, jsonl_output: str) -> str:
        """
        Parse JSONL output from `codex exec --json --ephemeral`.

        Extracts the agent's response from JSON events.
        Looks for: item.completed events with type="agent_message".
        """
        if not jsonl_output or not jsonl_output.strip():
            return ""

        agent_messages = []
        for line in jsonl_output.strip().split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)

                # Extract from item.completed events with agent_message type
                if event.get("type") == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        text = item.get("text", "")
                        if text:
                            agent_messages.append(text)

            except json.JSONDecodeError:
                # Skip unparseable lines
                continue

        return "\n".join(agent_messages).strip()
