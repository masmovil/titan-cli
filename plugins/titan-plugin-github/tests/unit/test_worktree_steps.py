"""
Unit tests for worktree steps.

Focus: cleanup must never stop the workflow. It runs after the review has been
submitted, and it also has to tolerate a run where worktree creation failed —
returning Exit in either case would abort the remaining steps.
"""

from unittest.mock import Mock

import pytest
from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import WorkflowContext
from titan_cli.engine.results import Skip, Success
from titan_plugin_github.steps.worktree_steps import cleanup_worktree_step


class _FakeTextual:
    def begin_step(self, _name):
        pass

    def end_step(self, _status):
        pass

    def dim_text(self, _text):
        pass

    def warning_text(self, _text):
        pass

    def success_text(self, _text):
        pass

    class _Loading:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def loading(self, _text):
        return self._Loading()


def _make_context(*, worktree_created=True, worktree_path="/tmp/wt", with_git=True):
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    if with_git:
        ctx.git = Mock()
        ctx.git.remove_worktree.return_value = ClientSuccess(data=None, message="Removed")
    else:
        ctx.git = None
    ctx.data["worktree_created"] = worktree_created
    if worktree_path is not None:
        ctx.data["worktree_path"] = worktree_path
    return ctx


@pytest.mark.unit
class TestCleanupWorktreeStep:
    def test_successful_cleanup_returns_success(self):
        ctx = _make_context()

        result = cleanup_worktree_step(ctx)

        assert isinstance(result, Success)
        ctx.git.remove_worktree.assert_called_once_with("/tmp/wt", force=True)

    def test_nothing_to_clean_up_skips_instead_of_exiting(self):
        """A failed worktree creation must not abort everything downstream."""
        ctx = _make_context(worktree_created=False)

        result = cleanup_worktree_step(ctx)

        assert isinstance(result, Skip)

    def test_missing_path_skips(self):
        ctx = _make_context(worktree_path=None)

        result = cleanup_worktree_step(ctx)

        assert isinstance(result, Skip)

    def test_missing_git_client_skips(self):
        ctx = _make_context(with_git=False)

        result = cleanup_worktree_step(ctx)

        assert isinstance(result, Skip)

    def test_failed_removal_skips(self):
        ctx = _make_context()
        ctx.git.remove_worktree.return_value = ClientError(
            error_message="not a working tree", error_code="WORKTREE_REMOVE_ERROR"
        )

        result = cleanup_worktree_step(ctx)

        assert isinstance(result, Skip)
