"""Small PTY-backed bridge for interactive external AI CLIs."""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import sys
from dataclasses import dataclass
from typing import Any, TextIO


@dataclass(slots=True)
class InteractiveSessionResult:
    """Terminal state returned by the interactive session bridge."""

    exit_code: int


def run_interactive_session(
    cli_id: str,
    *,
    cwd: str | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> InteractiveSessionResult:
    """Bridge JSON commands from stdin to an interactive CLI through a PTY.

    Inbound commands are JSON Lines:

    ``{"type":"input","value":"hello"}``
    ``{"type":"close"}``

    All outbound messages are JSON Lines. PTY use is deliberate: several AI
    CLIs change their behavior or refuse to start when stdin is not a TTY.
    """
    pid, master_fd = pty.fork()
    if pid == 0:
        if cwd:
            os.chdir(cwd)
        os.execvp(cli_id, [cli_id])

    _write_event(output_stream, "session_started", cli_id=cli_id)
    input_fd = input_stream.fileno()
    closed = False
    reaped = False
    exit_code = 0

    try:
        while True:
            readable, _, _ = select.select([master_fd, input_fd], [], [], 0.25)
            if master_fd in readable:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    _write_event(
                        output_stream,
                        "output",
                        content=chunk.decode("utf-8", errors="replace"),
                    )
                else:
                    break

            if input_fd in readable and not closed:
                line = input_stream.readline()
                if not line:
                    closed = True
                    os.write(master_fd, b"\x04")
                    continue
                command = json.loads(line)
                command_type = command.get("type")
                if command_type == "input":
                    value = command.get("value", "")
                    if not isinstance(value, str):
                        raise ValueError("session input value must be a string")
                    os.write(master_fd, value.encode("utf-8") + b"\n")
                elif command_type == "close":
                    closed = True
                    os.write(master_fd, b"\x04")
                else:
                    raise ValueError(f"unsupported session command: {command_type}")

            waited_pid, status = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                exit_code = os.waitstatus_to_exitcode(status)
                reaped = True
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        if not reaped:
            os.kill(pid, signal.SIGTERM)
            _, status = os.waitpid(pid, 0)
            exit_code = os.waitstatus_to_exitcode(status)

    _write_event(output_stream, "session_exited", exit_code=exit_code)
    return InteractiveSessionResult(exit_code=exit_code)


def _write_event(output_stream: TextIO, event_type: str, **payload: Any) -> None:
    output_stream.write(json.dumps({"type": event_type, **payload}) + "\n")
    output_stream.flush()
