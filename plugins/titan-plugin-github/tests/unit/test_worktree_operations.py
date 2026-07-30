"""
Unit tests for worktree operations
"""


import pytest
from titan_cli.core.result import ClientError
from titan_plugin_github.operations.worktree_operations import (
    setup_worktree,
    cleanup_worktree,
    clear_stale_worktree,
    commit_in_worktree,
)


@pytest.mark.unit
class TestSetupWorktree:
    """Test worktree setup"""

    def test_creates_worktree_successfully(self, mock_git_client):
        """Test successful worktree creation"""
        abs_path, success = setup_worktree(
            mock_git_client,
            pr_number=123,
            branch="feature-branch",
            base_path=".titan/worktrees"
        )

        assert success is True
        assert "titan-review-123" in abs_path
        mock_git_client.fetch_refspec.assert_called_once_with(
            "origin",
            "pull/123/head:refs/titan/review/pr-123",
        )
        mock_git_client.create_worktree.assert_called_once()
        assert mock_git_client.create_worktree.call_args.kwargs["branch"] == "refs/titan/review/pr-123"

    def test_removes_existing_worktree_before_creating(self, mock_git_client):
        """Test that existing worktree is removed first"""
        setup_worktree(mock_git_client, 123, "feature-branch")

        mock_git_client.remove_worktree.assert_called_once()
        mock_git_client.create_worktree.assert_called_once()

    def test_prunes_stale_metadata_before_creating(self, mock_git_client):
        """A previous run whose directory vanished leaves metadata that makes
        'remove' fail and 'add' refuse the path — only prune clears it."""
        setup_worktree(mock_git_client, 123, "feature-branch")

        mock_git_client.prune_worktrees.assert_called_once()

    def test_creation_still_proceeds_when_remove_and_prune_fail(self, mock_git_client):
        """Neither cleanup step is a precondition: a clean path needs no cleanup."""
        mock_git_client.remove_worktree.side_effect = Exception("not a working tree")
        mock_git_client.prune_worktrees.side_effect = Exception("prune exploded")

        abs_path, success = setup_worktree(mock_git_client, 123, "feature-branch")

        assert success is True
        mock_git_client.create_worktree.assert_called_once()

    def test_handles_refspec_fetch_failure(self, mock_git_client):
        """Test handling of refspec fetch failure for fork PRs."""
        mock_git_client.fetch_refspec.return_value = ClientError(
            error_message="Fetch failed", error_code="FETCH_ERROR"
        )

        abs_path, success = setup_worktree(mock_git_client, 123, "feature-branch")

        assert success is False
        assert abs_path == ""
        mock_git_client.create_worktree.assert_not_called()

    def test_handles_creation_failure(self, mock_git_client):
        """Test handling of worktree creation failure"""
        mock_git_client.create_worktree.return_value = ClientError(
            error_message="Creation failed", error_code="WORKTREE_CREATE_ERROR"
        )

        abs_path, success = setup_worktree(mock_git_client, 123, "feature-branch")

        assert success is False
        assert abs_path == ""

    def test_uses_custom_base_path(self, mock_git_client):
        """Test using custom base path for worktrees"""
        abs_path, success = setup_worktree(
            mock_git_client,
            456,
            "branch",
            base_path="/custom/path"
        )

        assert success is True
        assert "titan-review-456" in abs_path


@pytest.mark.unit
class TestClearStaleWorktree:
    """Test making a worktree path reusable after a previous run left residue"""

    def test_removes_leftover_directory_git_does_not_know_about(
        self, mock_git_client, tmp_path
    ):
        """The residue git commands can't touch: a directory with no registration.
        'worktree add' refuses a non-empty path, so it must be deleted."""
        leftover = tmp_path / "titan-review-123"
        leftover.mkdir()
        (leftover / "some_file.txt").write_text("residue")

        clear_stale_worktree(mock_git_client, ".titan/worktrees/titan-review-123", str(leftover))

        assert not leftover.exists()

    def test_calls_remove_then_prune(self, mock_git_client, tmp_path):
        clear_stale_worktree(mock_git_client, "wt/path", str(tmp_path / "absent"))

        mock_git_client.remove_worktree.assert_called_once_with("wt/path", force=True)
        mock_git_client.prune_worktrees.assert_called_once()

    def test_prunes_even_when_remove_raises(self, mock_git_client, tmp_path):
        """'remove' fails with "not a working tree" for exactly the stale-metadata
        case prune exists to fix — it must not short-circuit the prune."""
        mock_git_client.remove_worktree.side_effect = Exception("not a working tree")

        clear_stale_worktree(mock_git_client, "wt/path", str(tmp_path / "absent"))

        mock_git_client.prune_worktrees.assert_called_once()

    def test_removes_directory_even_when_git_steps_raise(self, mock_git_client, tmp_path):
        leftover = tmp_path / "titan-review-999"
        leftover.mkdir()
        mock_git_client.remove_worktree.side_effect = Exception("boom")
        mock_git_client.prune_worktrees.side_effect = Exception("boom")

        clear_stale_worktree(mock_git_client, "wt/path", str(leftover))

        assert not leftover.exists()

    def test_no_directory_removal_without_absolute_path(self, mock_git_client):
        clear_stale_worktree(mock_git_client, "wt/path")

        mock_git_client.remove_worktree.assert_called_once()
        mock_git_client.prune_worktrees.assert_called_once()

    def test_tolerates_missing_directory(self, mock_git_client, tmp_path):
        clear_stale_worktree(mock_git_client, "wt/path", str(tmp_path / "never_existed"))

    def test_leaves_a_file_at_that_path_untouched(self, mock_git_client, tmp_path):
        """Only directories are worktree residue; a file there is someone else's."""
        not_a_dir = tmp_path / "titan-review-1"
        not_a_dir.write_text("unrelated")

        clear_stale_worktree(mock_git_client, "wt/path", str(not_a_dir))

        assert not_a_dir.exists()


@pytest.mark.unit
class TestCleanupWorktree:
    """Test worktree cleanup"""

    def test_removes_worktree_successfully(self, mock_git_client):
        """Test successful worktree removal"""
        success = cleanup_worktree(mock_git_client, ".titan/worktrees/titan-review-123")

        assert success is True
        mock_git_client.remove_worktree.assert_called_once_with(
            ".titan/worktrees/titan-review-123",
            force=True
        )

    def test_handles_removal_failure(self, mock_git_client):
        """Test handling of removal failure"""
        mock_git_client.remove_worktree.return_value = ClientError(
            error_message="Removal failed", error_code="WORKTREE_REMOVE_ERROR"
        )

        success = cleanup_worktree(mock_git_client, "/path/to/worktree")

        assert success is False


@pytest.mark.unit
class TestCommitInWorktree:
    """Test creating commits in worktree"""

    def test_creates_commit_with_all_changes(self, mock_git_client):
        """Test creating commit with all changes staged"""
        commit_hash = commit_in_worktree(
            mock_git_client,
            "/tmp/worktree",
            "Fix bug in module",
            add_all=True,
            no_verify=False
        )

        assert commit_hash == "abc123def456789abc123def456789abc1234567"
        mock_git_client.commit_in_worktree.assert_called_once_with(
            "/tmp/worktree", "Fix bug in module", True, False
        )

    def test_creates_commit_without_staging(self, mock_git_client):
        """Test creating commit without staging changes"""
        commit_in_worktree(
            mock_git_client,
            "/tmp/worktree",
            "Commit message",
            add_all=False,
            no_verify=False
        )

        mock_git_client.commit_in_worktree.assert_called_once_with(
            "/tmp/worktree", "Commit message", False, False
        )

    def test_uses_no_verify_flag(self, mock_git_client):
        """Test passing no_verify flag through to client"""
        commit_in_worktree(
            mock_git_client,
            "/tmp/worktree",
            "Message",
            add_all=False,
            no_verify=True
        )

        mock_git_client.commit_in_worktree.assert_called_once_with(
            "/tmp/worktree", "Message", False, True
        )

    def test_handles_commit_failure(self, mock_git_client):
        """Test handling of commit failure"""
        mock_git_client.commit_in_worktree.return_value = ClientError(
            error_message="Nothing to commit", error_code="WORKTREE_COMMIT_ERROR"
        )

        with pytest.raises(Exception, match="Failed to commit in worktree"):
            commit_in_worktree(
                mock_git_client,
                "/tmp/worktree",
                "Message",
                add_all=True,
                no_verify=False
            )
