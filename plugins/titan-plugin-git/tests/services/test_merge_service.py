"""
Unit tests for Merge Service
"""

import pytest
from unittest.mock import Mock

from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_git.clients.services.merge_service import MergeService
from titan_plugin_git.exceptions import GitCommandError
from titan_plugin_git.models.view.merge import MergeStatus


@pytest.fixture
def mock_git_network():
    """Mock GitNetwork instance"""
    return Mock()


@pytest.fixture
def service(mock_git_network):
    return MergeService(mock_git_network)


def _router(
    merge_output="",
    conflicted="",
    merge_head="",
    head_before="aaa",
    head_after="aaa",
    second_parent="",
):
    """
    Build a run_command side effect that answers per git subcommand.

    Lets each test describe the repo state instead of ordering return values.
    The two plain `rev-parse HEAD` calls are answered in order: the first is
    HEAD before the merge, the second is HEAD after it.
    """
    state = {"head_calls": 0}

    def side_effect(args, *_, **__):
        if args[1] == "merge":
            return merge_output
        if args[1] == "diff":
            return conflicted
        if args[1] == "rev-parse":
            if args[-1] == "MERGE_HEAD":
                return merge_head
            if args[-1] == "HEAD^2":
                return second_parent
            state["head_calls"] += 1
            return head_before if state["head_calls"] == 1 else head_after
        return ""
    return side_effect


@pytest.mark.unit
class TestMergeServiceMerge:
    """Test MergeService.merge()"""

    def _merge_call(self, mock_git_network):
        """Return the run_command call that actually ran `git merge`."""
        return next(
            call for call in mock_git_network.run_command.call_args_list
            if call.args[0][1] == "merge"
        )

    def test_merge_uses_no_edit(self, service, mock_git_network):
        """Should never open an editor."""
        mock_git_network.run_command.side_effect = _router()

        service.merge("origin/develop")

        assert self._merge_call(mock_git_network).args[0] == [
            "git", "merge", "--no-edit", "origin/develop"
        ]

    def test_merge_does_not_raise_on_failure(self, service, mock_git_network):
        """Should run the merge with check=False so conflicts do not raise."""
        mock_git_network.run_command.side_effect = _router()

        service.merge("origin/develop")

        assert self._merge_call(mock_git_network).kwargs["check"] is False

    def test_merge_no_ff(self, service, mock_git_network):
        """Should pass --no-ff when requested."""
        mock_git_network.run_command.side_effect = _router()

        service.merge("origin/develop", no_ff=True)

        assert "--no-ff" in self._merge_call(mock_git_network).args[0]

    def test_up_to_date(self, service, mock_git_network):
        """Should classify a merge that did not move HEAD as UP_TO_DATE."""
        mock_git_network.run_command.side_effect = _router(
            head_before="aaa", head_after="aaa"
        )

        result = service.merge("origin/develop", target_branch="feature/x")

        assert isinstance(result, ClientSuccess)
        assert result.data.status == MergeStatus.UP_TO_DATE
        assert result.data.conflicted_files == []

    def test_fast_forward(self, service, mock_git_network):
        """Should classify a moved HEAD without a second parent as FAST_FORWARD."""
        mock_git_network.run_command.side_effect = _router(
            head_before="aaa", head_after="bbb", second_parent=""
        )

        result = service.merge("origin/develop")

        assert result.data.status == MergeStatus.FAST_FORWARD

    def test_merge_commit(self, service, mock_git_network):
        """Should classify a new merge commit as MERGED."""
        mock_git_network.run_command.side_effect = _router(
            head_before="aaa", head_after="bbb", second_parent="ccc"
        )

        result = service.merge("origin/develop")

        assert result.data.status == MergeStatus.MERGED

    def test_conflicted(self, service, mock_git_network):
        """Should classify a stopped merge and list the conflicted files."""
        mock_git_network.run_command.side_effect = _router(
            conflicted="src/app.py\nsrc/other.py",
            merge_head="abc123",
        )

        result = service.merge("origin/develop", target_branch="feature/x")

        assert isinstance(result, ClientSuccess)
        assert result.data.status == MergeStatus.CONFLICTED
        assert result.data.conflicted_files == ["src/app.py", "src/other.py"]
        assert result.data.has_conflicts is True

    def test_carries_refs_into_result(self, service, mock_git_network):
        """Should keep source and target refs for display."""
        mock_git_network.run_command.side_effect = _router()

        result = service.merge("origin/develop", target_branch="feature/x")

        assert result.data.source_ref == "origin/develop"
        assert result.data.target_branch == "feature/x"

    def test_merge_command_error(self, service, mock_git_network):
        """Should return ClientError when git itself fails."""
        mock_git_network.run_command.side_effect = GitCommandError("boom")

        result = service.merge("origin/develop")

        assert isinstance(result, ClientError)
        assert result.error_code == "MERGE_ERROR"


@pytest.mark.unit
class TestMergeServiceConflicts:
    """Test MergeService.get_conflicted_files() and is_merge_in_progress()"""

    def test_get_conflicted_files(self, service, mock_git_network):
        """Should parse unmerged paths one per line."""
        mock_git_network.run_command.return_value = "a.py\nb.py"

        result = service.get_conflicted_files()

        assert isinstance(result, ClientSuccess)
        assert result.data == ["a.py", "b.py"]
        assert mock_git_network.run_command.call_args.args[0] == [
            "git", "diff", "--name-only", "--diff-filter=U"
        ]

    def test_get_conflicted_files_empty(self, service, mock_git_network):
        """Should return an empty list when nothing is unmerged."""
        mock_git_network.run_command.return_value = ""

        result = service.get_conflicted_files()

        assert result.data == []

    def test_get_conflicted_files_error(self, service, mock_git_network):
        """Should return ClientError when git fails."""
        mock_git_network.run_command.side_effect = GitCommandError("boom")

        result = service.get_conflicted_files()

        assert isinstance(result, ClientError)
        assert result.error_code == "CONFLICT_CHECK_ERROR"

    def test_merge_in_progress(self, service, mock_git_network):
        """Should report True when MERGE_HEAD resolves."""
        mock_git_network.run_command.return_value = "abc123"

        result = service.is_merge_in_progress()

        assert result.data is True

    def test_merge_not_in_progress(self, service, mock_git_network):
        """Should report False when MERGE_HEAD is absent."""
        mock_git_network.run_command.return_value = ""

        result = service.is_merge_in_progress()

        assert result.data is False


@pytest.mark.unit
class TestMergeServiceCompletion:
    """Test MergeService.stage_all(), continue_merge() and abort_merge()"""

    def test_stage_all(self, service, mock_git_network):
        """Should stage everything including untracked files."""
        mock_git_network.run_command.return_value = ""

        result = service.stage_all()

        assert isinstance(result, ClientSuccess)
        assert mock_git_network.run_command.call_args.args[0] == ["git", "add", "--all"]

    def test_stage_all_error(self, service, mock_git_network):
        """Should return ClientError when staging fails."""
        mock_git_network.run_command.side_effect = GitCommandError("boom")

        result = service.stage_all()

        assert isinstance(result, ClientError)
        assert result.error_code == "STAGE_ERROR"

    def test_continue_merge_commits_without_editor(self, service, mock_git_network):
        """Should commit git's prepared merge message without opening an editor."""
        mock_git_network.run_command.side_effect = ["", "abc123def456"]

        result = service.continue_merge()

        assert isinstance(result, ClientSuccess)
        assert result.data == "abc123def456"
        commit_call = mock_git_network.run_command.call_args_list[0]
        assert commit_call.args[0] == ["git", "commit", "--no-edit"]

    def test_continue_merge_error(self, service, mock_git_network):
        """Should return ClientError when the commit fails."""
        mock_git_network.run_command.side_effect = GitCommandError("boom")

        result = service.continue_merge()

        assert isinstance(result, ClientError)
        assert result.error_code == "MERGE_CONTINUE_ERROR"

    def test_abort_merge(self, service, mock_git_network):
        """Should run git merge --abort."""
        mock_git_network.run_command.return_value = ""

        result = service.abort_merge()

        assert isinstance(result, ClientSuccess)
        assert mock_git_network.run_command.call_args.args[0] == ["git", "merge", "--abort"]

    def test_abort_merge_error(self, service, mock_git_network):
        """Should return ClientError when the abort fails."""
        mock_git_network.run_command.side_effect = GitCommandError("boom")

        result = service.abort_merge()

        assert isinstance(result, ClientError)
        assert result.error_code == "MERGE_ABORT_ERROR"
