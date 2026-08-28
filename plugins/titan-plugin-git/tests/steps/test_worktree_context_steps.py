"""Tests for routing workflows through an isolated worktree."""

from unittest.mock import MagicMock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_git.steps.worktree_context_steps import (
    activate_worktree_context,
    cleanup_worktree_context,
)


def test_activate_and_cleanup_worktree_context(tmp_path):
    original_git = MagicMock()
    original_git.main_branch = "main"
    original_git.default_remote = "origin"
    original_git.remove_worktree.return_value = ClientSuccess(data=None)
    github = MagicMock()
    ctx = WorkflowContext(
        textual=MagicMock(),
        git=original_git,
        github=github,
        data={
            "worktree_path": str(tmp_path),
            "base_branch": "develop",
            "remote": "upstream",
            "project_root": "/original/project",
        },
    )

    activate_result = activate_worktree_context(ctx)

    assert isinstance(activate_result, Success)
    assert ctx.git is not original_git
    assert ctx.git.repo_path == str(tmp_path)
    assert ctx.git.main_branch == "develop"
    assert ctx.git.default_remote == "upstream"
    assert github.git_client is ctx.git
    assert ctx.data["project_root"] == str(tmp_path)

    cleanup_result = cleanup_worktree_context(ctx)

    assert isinstance(cleanup_result, Success)
    assert ctx.git is original_git
    assert github.git_client is original_git
    assert ctx.data["project_root"] == "/original/project"
    original_git.remove_worktree.assert_called_once_with(
        path=str(tmp_path), force=False
    )


def test_activate_rejects_missing_worktree_path(tmp_path):
    ctx = WorkflowContext(
        textual=MagicMock(),
        git=MagicMock(),
        data={"worktree_path": str(tmp_path / "missing")},
    )

    result = activate_worktree_context(ctx)

    assert isinstance(result, Error)
    assert "valid worktree_path" in result.message


def test_cleanup_reports_worktree_removal_failure(tmp_path):
    original_git = MagicMock()
    original_git.main_branch = "develop"
    original_git.default_remote = "origin"
    original_git.remove_worktree.return_value = ClientError(
        error_message="worktree contains changes"
    )
    ctx = WorkflowContext(
        textual=MagicMock(),
        git=original_git,
        data={"worktree_path": str(tmp_path)},
    )
    assert isinstance(activate_worktree_context(ctx), Success)

    result = cleanup_worktree_context(ctx)

    assert isinstance(result, Error)
    assert "worktree contains changes" in result.message
    assert ctx.git is original_git
