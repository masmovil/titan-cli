"""
Subprocess execution helpers for the secret use-primitives.

The value crosses into a subprocess as an *effect* (stdin, a single env
variable, a tempfile) and never comes back to the caller: the result carries
exit code and redacted output only.
"""

import os
import subprocess
from dataclasses import dataclass

from .redaction import redact

# Environment for run_with_secret_env. Unlike regular command steps (which
# inherit the console environment), a command that receives a secret through
# the environment runs on a minimal one: the injected variable must be the
# only sensitive thing in there, so a tool that dumps its env leaks one value
# at most — and never an unrelated one.
MINIMAL_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM",
    "LANG", "LANGUAGE", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
})

MINIMAL_ENV_PREFIXES = ("LC_", "XDG_")


@dataclass
class SecureCommandResult:
    """Outcome of a use-primitive subprocess. Output is already redacted."""

    exit_code: int
    stdout: str
    stderr: str
    cancelled: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.cancelled


CANCELLED_RESULT = SecureCommandResult(
    exit_code=-1, stdout="", stderr="No secret was provided.", cancelled=True
)


def build_minimal_env(extra_allowlist: list[str] | None = None) -> dict[str, str]:
    """Minimal subprocess environment plus explicitly allowed extra names."""
    allowed = set(MINIMAL_ENV_ALLOWLIST)
    if extra_allowlist:
        allowed.update(name for name in extra_allowlist if isinstance(name, str))
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed or key.startswith(MINIMAL_ENV_PREFIXES)
    }


# Generous ceiling for use-primitive subprocesses (GPG decrypt, token
# exchanges): long enough for slow crypto or a captive network, short enough
# that a tool waiting on input cannot hang the workflow thread forever.
DEFAULT_COMMAND_TIMEOUT = 300.0


def run_redacted(
    command: list[str],
    *,
    stdin_value: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = DEFAULT_COMMAND_TIMEOUT,
) -> SecureCommandResult:
    """Run `command`, optionally feeding a secret on stdin, redacting output."""
    try:
        completed = subprocess.run(
            command,
            input=stdin_value,
            # Without an explicit stdin the child would inherit the parent's,
            # letting an input-waiting tool block the workflow thread.
            stdin=subprocess.DEVNULL if stdin_value is None else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return SecureCommandResult(
            exit_code=124,  # shell convention for a timeout
            stdout=redact(stdout),
            stderr=redact(stderr or f"Command timed out after {timeout}s"),
        )
    except FileNotFoundError as e:
        # Shell convention: 127 = command not found. Surfacing it as a result
        # (instead of an exception) lets callers tell "the tool is missing"
        # apart from "the credential failed" — the retry logic must never
        # treat a missing binary as a stale secret.
        return SecureCommandResult(exit_code=127, stdout="", stderr=redact(str(e)))
    except PermissionError as e:
        return SecureCommandResult(exit_code=126, stdout="", stderr=redact(str(e)))
    return SecureCommandResult(
        exit_code=completed.returncode,
        stdout=redact(completed.stdout or ""),
        stderr=redact(completed.stderr or ""),
    )
