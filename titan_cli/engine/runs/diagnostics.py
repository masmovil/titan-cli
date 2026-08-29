"""Safe runtime diagnostics for headless workflow runs."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from titan_cli import __version__
from titan_cli.external_cli.adapters.base import resolve_cli_executable


def build_runtime_diagnostics() -> dict[str, Any]:
    """Describe the execution environment without exposing credentials."""
    claude_path = resolve_cli_executable("claude")
    return {
        "titan_version": __version__,
        "python_executable": sys.executable,
        "titan_entrypoint": os.path.abspath(sys.argv[0]),
        "path": os.environ.get("PATH", ""),
        "claude_configured_path": os.environ.get("TITAN_CLAUDE_PATH"),
        "claude_resolved_path": claude_path,
        "claude_version": _read_cli_version(claude_path),
    }


def _read_cli_version(executable: str | None) -> str | None:
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (result.stdout or result.stderr or "").strip()
    return output.splitlines()[0][:200] if output else None
