"""
Unit tests for Worktree Service
"""

import pytest
from unittest.mock import Mock
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_git.clients.services.worktree_service import WorktreeService
from titan_plugin_git.exceptions import GitError


@pytest.fixture
def mock_git_network():
    """Mock GitNetwork instance"""
    return Mock()


@pytest.mark.unit
class TestWorktreeServiceCreate:
    """Test WorktreeService.create_worktree()."""

    def test_create_branch_from_explicit_start_point(self, mock_git_network):
        """Create an attached branch from the requested remote base ref."""
        mock_git_network.run_command.return_value = ""
        service = WorktreeService(mock_git_network)

        result = service.create_worktree(
            "/tmp/worktree",
            "feature/PROJ-123",
            create_branch=True,
            start_point="origin/develop",
        )

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            [
                "git",
                "worktree",
                "add",
                "-b",
                "feature/PROJ-123",
                "/tmp/worktree",
                "origin/develop",
            ]
        )


@pytest.mark.unit
class TestWorktreeServiceCheckoutBranch:
    """Test WorktreeService.checkout_branch_in_worktree()"""

    def test_checkout_existing_branch(self, mock_git_network):
        """Test checking out an existing branch"""
        mock_git_network.run_command.return_value = ""

        service = WorktreeService(mock_git_network)
        result = service.checkout_branch_in_worktree("/tmp/worktree", "feature-branch")

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "-C", "/tmp/worktree", "checkout", "-b", "feature-branch"],
            cwd="/tmp/worktree"
        )

    def test_checkout_with_force_creates_or_resets_branch(self, mock_git_network):
        """Test force checkout uses -B flag"""
        mock_git_network.run_command.return_value = ""

        service = WorktreeService(mock_git_network)
        result = service.checkout_branch_in_worktree("/tmp/worktree", "notes/release", force=True)

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "-C", "/tmp/worktree", "checkout", "-B", "notes/release"],
            cwd="/tmp/worktree"
        )

    def test_checkout_error_returns_client_error(self, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitError("branch already exists")

        service = WorktreeService(mock_git_network)
        result = service.checkout_branch_in_worktree("/tmp/worktree", "feature")

        assert isinstance(result, ClientError)
        assert result.error_code == "WORKTREE_CHECKOUT_ERROR"
        assert "branch already exists" in result.error_message


@pytest.mark.unit
class TestWorktreeServicePrune:
    """Test WorktreeService.prune_worktrees()"""

    def test_prune_runs_git_worktree_prune(self, mock_git_network):
        mock_git_network.run_command.return_value = ""

        service = WorktreeService(mock_git_network)
        result = service.prune_worktrees()

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(["git", "worktree", "prune"])

    def test_prune_error_returns_client_error(self, mock_git_network):
        mock_git_network.run_command.side_effect = GitError("not a git repository")

        service = WorktreeService(mock_git_network)
        result = service.prune_worktrees()

        assert isinstance(result, ClientError)
        assert result.error_code == "WORKTREE_PRUNE_ERROR"


@pytest.mark.unit
class TestWorktreeServiceCommit:
    """Test WorktreeService.commit_in_worktree()"""

    def test_commit_with_add_all(self, mock_git_network):
        """Test commit stages all files before committing"""
        mock_git_network.run_command.side_effect = [
            "",                 # git add --all
            "",                 # git commit
            "abc123def456\n",   # git rev-parse HEAD
        ]

        service = WorktreeService(mock_git_network)
        result = service.commit_in_worktree("/tmp/worktree", "Fix bug", add_all=True)

        assert isinstance(result, ClientSuccess)
        assert result.data == "abc123def456"
        calls = mock_git_network.run_command.call_args_list
        assert ["git", "-C", "/tmp/worktree", "add", "--all"] in [c.args[0] for c in calls]

    def test_commit_without_add_all_skips_staging(self, mock_git_network):
        """Test commit without add_all doesn't run git add"""
        mock_git_network.run_command.side_effect = [
            "",                 # git commit
            "def456abc123\n",   # git rev-parse HEAD
        ]

        service = WorktreeService(mock_git_network)
        result = service.commit_in_worktree("/tmp/worktree", "Fix bug", add_all=False)

        assert isinstance(result, ClientSuccess)
        calls = mock_git_network.run_command.call_args_list
        assert not any("add" in str(c) for c in calls)

    def test_commit_with_no_verify(self, mock_git_network):
        """Test commit passes --no-verify flag"""
        mock_git_network.run_command.side_effect = ["", "", "hash123\n"]

        service = WorktreeService(mock_git_network)
        service.commit_in_worktree("/tmp/worktree", "Message", add_all=True, no_verify=True)

        calls = mock_git_network.run_command.call_args_list
        commit_call = next(c for c in calls if "commit" in str(c))
        assert "--no-verify" in commit_call.args[0]

    def test_commit_returns_stripped_hash(self, mock_git_network):
        """Test commit hash is stripped of whitespace"""
        mock_git_network.run_command.side_effect = ["", "  abc123  \n"]

        service = WorktreeService(mock_git_network)
        result = service.commit_in_worktree("/tmp/worktree", "Msg", add_all=False)

        assert result.data == "abc123"

    def test_commit_error_returns_client_error(self, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitError("nothing to commit")

        service = WorktreeService(mock_git_network)
        result = service.commit_in_worktree("/tmp/worktree", "Msg", add_all=True)

        assert isinstance(result, ClientError)
        assert result.error_code == "WORKTREE_COMMIT_ERROR"
