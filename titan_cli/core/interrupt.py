"""
Cooperative interruption for blocking calls made from workflow threads.

A workflow runs on a non-daemon executor thread that the interpreter joins at
exit. The ask_* prompts already poll `app.is_running` so they unblock when the
user quits mid-prompt, but a call that blocks inside foreign code - an AI SDK's
HTTP request, a headless CLI subprocess - has no loop to poll from. Quitting
the TUI while one is in flight used to hang the console until the call
finished, needing a second Ctrl+C to kill the join.

`run_interruptible` closes that gap: it moves the blocking call onto a daemon
thread (which the interpreter never joins) and polls an abort check from the
workflow thread. When the TUI closes, the workflow thread raises
`WorkflowAborted` and dies cleanly; the abandoned call finishes alone on the
daemon thread and its result is discarded.

The abort check is process-global rather than threaded through every layer
because only one workflow runs at a time and the transports that need it
(AIClient, headless adapters) sit four layers below the screen that knows
whether the app is alive. When no check is registered - unit tests, headless
usage outside the TUI - `run_interruptible` calls the function inline and
behaves exactly like not being there.
"""

import threading
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

_POLL_INTERVAL_SECONDS = 0.5

_abort_check: Optional[Callable[[], bool]] = None


class WorkflowAborted(BaseException):
    """
    The TUI closed while a workflow call was in flight.

    Inherits `BaseException` deliberately: transports and the step loop catch
    `Exception` broadly to convert failures into step errors, and an abort must
    not be converted - it has to unwind the whole workflow thread, like
    `KeyboardInterrupt` would on the main thread.
    """


def set_abort_check(check: Callable[[], bool]) -> None:
    """Register the check consulted by `run_interruptible` (True = abort)."""
    global _abort_check
    _abort_check = check


def clear_abort_check() -> None:
    """Remove the registered abort check."""
    global _abort_check
    _abort_check = None


def abort_requested() -> bool:
    """Whether the registered check currently asks to abort."""
    check = _abort_check
    if check is None:
        return False
    try:
        return bool(check())
    except Exception:
        # A check that can no longer answer (app torn down mid-call) means the
        # app is gone, which is exactly the abort condition.
        return True


def run_interruptible(fn: Callable[[], T]) -> T:
    """
    Run a blocking call so the calling thread can abandon it on app exit.

    Runs `fn` on a daemon thread and polls the abort check every half second.
    Returns `fn`'s result or re-raises its exception. Raises `WorkflowAborted`
    if the check fires first; `fn` keeps running on the daemon thread but its
    outcome is discarded and the thread cannot block interpreter shutdown.

    With no abort check registered, calls `fn` inline.
    """
    if _abort_check is None:
        return fn()

    outcome: dict = {}
    done = threading.Event()

    def _target() -> None:
        try:
            outcome["result"] = fn()
        except BaseException as e:
            outcome["error"] = e
        finally:
            done.set()

    thread = threading.Thread(target=_target, name="titan-interruptible-call", daemon=True)
    thread.start()

    while not done.wait(timeout=_POLL_INTERVAL_SECONDS):
        if abort_requested():
            raise WorkflowAborted("Application closed while a blocking call was in flight")

    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]
