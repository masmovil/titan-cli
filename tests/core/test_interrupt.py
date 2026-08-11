"""Tests for cooperative interruption of blocking workflow calls."""

import threading
import time

import pytest

from titan_cli.core.interrupt import (
    WorkflowAborted,
    abort_requested,
    clear_abort_check,
    run_interruptible,
    set_abort_check,
)


@pytest.fixture(autouse=True)
def _clean_abort_check():
    clear_abort_check()
    yield
    clear_abort_check()


class TestWithoutAbortCheck:
    def test_runs_inline_and_returns_result(self):
        assert run_interruptible(lambda: 42) == 42

    def test_propagates_exception(self):
        with pytest.raises(ValueError, match="boom"):
            run_interruptible(lambda: (_ for _ in ()).throw(ValueError("boom")))

    def test_abort_requested_is_false(self):
        assert abort_requested() is False


class TestWithAbortCheck:
    def test_returns_result_when_not_aborted(self):
        set_abort_check(lambda: False)
        assert run_interruptible(lambda: "ok") == "ok"

    def test_propagates_exception_when_not_aborted(self):
        set_abort_check(lambda: False)

        def fail():
            raise RuntimeError("provider down")

        with pytest.raises(RuntimeError, match="provider down"):
            run_interruptible(fail)

    def test_raises_workflow_aborted_while_call_is_blocked(self):
        aborted = threading.Event()
        set_abort_check(aborted.is_set)

        release = threading.Event()

        def blocking_call():
            release.wait(timeout=30)
            return "too late"

        aborted.set()
        started = time.monotonic()
        with pytest.raises(WorkflowAborted):
            run_interruptible(blocking_call)
        # It escaped by polling, not by waiting the call out.
        assert time.monotonic() - started < 5
        release.set()

    def test_workflow_aborted_is_not_an_exception_subclass(self):
        # Transports and the step loop catch `Exception` broadly; an abort must
        # pass through those handlers untouched.
        assert not issubclass(WorkflowAborted, Exception)
        assert issubclass(WorkflowAborted, BaseException)

    def test_failing_check_counts_as_abort(self):
        def broken_check():
            raise RuntimeError("app torn down")

        set_abort_check(broken_check)
        assert abort_requested() is True
