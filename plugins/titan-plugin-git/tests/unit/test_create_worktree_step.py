"""
Unit tests for create_worktree step (base branch resolution).
"""

from unittest.mock import Mock

from titan_cli.core.result import ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_git.steps.create_worktree_step import create_worktree


class MockTextual:
    def __init__(self):
        self.begin_step = Mock()
        self.end_step = Mock()
        self.text = Mock()
        self.primary_text = Mock()
        self.dim_text = Mock()
        self.error_text = Mock()
        self.success_text = Mock()
        self.warning_text = Mock()


def make_git_client(main_branch="main"):
    git = Mock()
    git.main_branch = main_branch
    git.default_remote = "origin"
    git.repo_path = "."
    git.fetch.return_value = ClientSuccess(data=None, message="ok")
    git.list_worktrees.return_value = ClientSuccess(data=[], message="ok")
    git.create_worktree.return_value = ClientSuccess(data=None, message="ok")
    return git


def make_context(git_client, **data):
    ctx = WorkflowContext(textual=MockTextual(), git=git_client)
    ctx.data.update(data)
    return ctx


def test_create_worktree_uses_context_base_branch(tmp_path):
    git = make_git_client(main_branch="develop")
    worktree_path = str(tmp_path / "wt")
    ctx = make_context(git, base_branch="rc/26.18.2", path=worktree_path)

    result = create_worktree(ctx)

    assert isinstance(result, Success)
    git.create_worktree.assert_called_once()
    assert git.create_worktree.call_args.kwargs["branch"] == "origin/rc/26.18.2"
    assert result.metadata["base_branch"] == "rc/26.18.2"
    assert result.metadata["worktree_path"] == worktree_path


def test_create_worktree_falls_back_to_main_branch(tmp_path):
    git = make_git_client(main_branch="develop")
    ctx = make_context(git, path=str(tmp_path / "wt"))

    result = create_worktree(ctx)

    assert isinstance(result, Success)
    git.create_worktree.assert_called_once()
    assert git.create_worktree.call_args.kwargs["branch"] == "origin/develop"
    assert result.metadata["base_branch"] == "develop"


def test_create_worktree_errors_without_base_branch(tmp_path):
    git = make_git_client(main_branch=None)
    ctx = make_context(git, path=str(tmp_path / "wt"))

    result = create_worktree(ctx)

    assert isinstance(result, Error)
    assert "base_branch" in result.message
    assert "main_branch" in result.message
    git.create_worktree.assert_not_called()
    ctx.textual.end_step.assert_called_once_with("error")
