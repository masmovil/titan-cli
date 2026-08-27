"""
Unit tests for Commit Service
"""

import pytest
from unittest.mock import Mock
from unittest.mock import patch
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_git.clients.services.commit_service import CommitService
from titan_plugin_git.exceptions import GitCommandError


@pytest.fixture
def mock_git_network():
    """Mock GitNetwork instance"""
    return Mock()


@pytest.fixture
def service(mock_git_network):
    return CommitService(mock_git_network, main_branch="main", default_remote="origin")


@pytest.mark.unit
class TestCommitServiceCommit:
    """Test CommitService.commit()"""

    def test_commit_basic(self, service, mock_git_network):
        """Test basic commit without staging"""
        mock_git_network.run_command.side_effect = ["", "abc123\n"]

        result = service.commit("feat: Add feature", all=False, no_verify=False)

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "commit", "-m", "feat: Add feature"] in calls

    def test_commit_with_all_stages_files(self, service, mock_git_network):
        """Test commit with all=True runs git add --all first"""
        mock_git_network.run_command.side_effect = ["", "", "abc123\n"]

        result = service.commit("fix: Bug", all=True, no_verify=False)

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--all"] in calls

    def test_commit_with_no_verify_appends_flag(self, service, mock_git_network):
        """Test commit with no_verify=True adds --no-verify flag"""
        mock_git_network.run_command.side_effect = ["", "abc123\n"]

        service.commit("msg", all=False, no_verify=True)

        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        commit_call = next(c for c in calls if "commit" in c)
        assert "--no-verify" in commit_call

    def test_commit_returns_hash(self, service, mock_git_network):
        """Test commit returns hash from rev-parse"""
        mock_git_network.run_command.side_effect = ["", "deadbeef123\n"]

        result = service.commit("msg", all=False, no_verify=False)

        assert isinstance(result, ClientSuccess)
        assert result.data == "deadbeef123\n"

    def test_commit_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("nothing to commit")

        result = service.commit("msg")

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"
        assert "nothing to commit" in result.error_message


@pytest.mark.unit
class TestCommitServiceGetCurrentCommit:
    """Test CommitService.get_current_commit()"""

    def test_returns_commit_hash(self, service, mock_git_network):
        """Test returns HEAD hash"""
        mock_git_network.run_command.return_value = "abc123def456\n"

        result = service.get_current_commit()

        assert isinstance(result, ClientSuccess)
        assert result.data == "abc123def456\n"
        mock_git_network.run_command.assert_called_once_with(
            ["git", "rev-parse", "HEAD"]
        )

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("not a git repo")

        result = service.get_current_commit()

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"


@pytest.mark.unit
class TestCommitServiceCommitFiles:
    """Test CommitService.commit_files()"""

    def test_commit_files_limits_commit_to_selected_paths(self, service, mock_git_network):
        """Test git commit is constrained to the selected pathspec"""
        mock_git_network.run_command.side_effect = ["", "", "abc123\n"]

        with patch("titan_plugin_git.clients.services.commit_service.os.path.exists", return_value=True):
            result = service.commit_files(["src/main.py"], "feat: Add feature", no_verify=True)

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--", "src/main.py"] in calls
        assert [
            "git", "commit", "-m", "feat: Add feature", "--no-verify", "--", "src/main.py"
        ] in calls

    def test_commit_files_handles_deleted_paths_with_pathspec(self, service, mock_git_network):
        """Test deleted tracked files are staged with git rm and committed by pathspec"""
        mock_git_network.run_command.side_effect = [
            "tracked",
            "",
            "",
            "deadbeef\n",
        ]

        with patch("titan_plugin_git.clients.services.commit_service.os.path.exists", return_value=False):
            result = service.commit_files(["removed.py"], "fix: Remove file", no_verify=False)

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "ls-files", "--error-unmatch", "removed.py"] in calls
        assert ["git", "rm", "--", "removed.py"] in calls
        assert ["git", "commit", "-m", "fix: Remove file", "--", "removed.py"] in calls

    def test_commit_files_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("commit failed")

        result = service.commit_files(["src/main.py"], "feat: Add feature")

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"


@pytest.mark.unit
class TestCommitServiceGetCommitSha:
    """Test CommitService.get_commit_sha()"""

    def test_resolves_ref_to_sha(self, service, mock_git_network):
        """Test resolves any git ref to SHA"""
        mock_git_network.run_command.return_value = "deadbeef\n"

        result = service.get_commit_sha("v1.0.0")

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(["git", "rev-parse", "v1.0.0"])

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test invalid ref returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("unknown revision")

        result = service.get_commit_sha("bad-ref")

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"


@pytest.mark.unit
class TestCommitServiceGetCommitsVsBase:
    """Test CommitService.get_commits_vs_base()"""

    def test_returns_commit_list(self, service, mock_git_network):
        """Test parses multi-line log output into list"""
        mock_git_network.run_command.return_value = "feat: A\nfix: B\nchore: C"

        result = service.get_commits_vs_base()

        assert isinstance(result, ClientSuccess)
        assert result.data == ["feat: A", "fix: B", "chore: C"]

    def test_empty_output_returns_empty_list(self, service, mock_git_network):
        """Test empty output (no commits ahead) returns empty list"""
        mock_git_network.run_command.return_value = ""

        result = service.get_commits_vs_base()

        assert isinstance(result, ClientSuccess)
        assert result.data == []

    def test_uses_main_branch_in_range(self, service, mock_git_network):
        """Test uses configured main_branch in git log range"""
        mock_git_network.run_command.return_value = ""

        service.get_commits_vs_base()

        args = mock_git_network.run_command.call_args.args[0]
        assert "main..HEAD" in args

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("fatal error")

        result = service.get_commits_vs_base()

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"


@pytest.mark.unit
class TestCommitServiceCountCommitsAhead:
    """Test CommitService.count_commits_ahead()"""

    def test_returns_count(self, service, mock_git_network):
        """Test parses integer from rev-list --count output"""
        mock_git_network.run_command.return_value = "3\n"

        result = service.count_commits_ahead("develop")

        assert isinstance(result, ClientSuccess)
        assert result.data == 3

    def test_zero_commits_ahead(self, service, mock_git_network):
        """Test zero commits ahead returns 0"""
        mock_git_network.run_command.return_value = "0\n"

        result = service.count_commits_ahead("develop")

        assert isinstance(result, ClientSuccess)
        assert result.data == 0

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("unknown branch")

        result = service.count_commits_ahead("develop")

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_COUNT_ERROR"


@pytest.mark.unit
class TestCommitServiceGetCommitsBetweenRefs:
    """Test CommitService.get_commits_between_refs()"""

    def test_returns_commit_list(self, service, mock_git_network):
        """Test parses multi-line log output into list"""
        mock_git_network.run_command.return_value = "feat: A\nfix: B\nchore: C"

        result = service.get_commits_between_refs("0.4.0", "HEAD")

        assert isinstance(result, ClientSuccess)
        assert result.data == ["feat: A", "fix: B", "chore: C"]
        mock_git_network.run_command.assert_called_once_with(
            ["git", "log", "0.4.0..HEAD", "--pretty=format:%s"]
        )

    def test_uses_head_by_default(self, service, mock_git_network):
        """Test default head_ref is HEAD"""
        mock_git_network.run_command.return_value = ""

        result = service.get_commits_between_refs("0.4.0")

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "log", "0.4.0..HEAD", "--pretty=format:%s"]
        )

    def test_empty_output_returns_empty_list(self, service, mock_git_network):
        """Test empty output returns empty list"""
        mock_git_network.run_command.return_value = ""

        result = service.get_commits_between_refs("0.4.0", "master")

        assert isinstance(result, ClientSuccess)
        assert result.data == []

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("unknown revision")

        result = service.get_commits_between_refs("bad-ref", "HEAD")

        assert isinstance(result, ClientError)
        assert result.error_code == "COMMIT_ERROR"


@pytest.mark.unit
class TestCommitServiceCountUnpushedCommits:
    """Test CommitService.count_unpushed_commits()"""

    def test_returns_unpushed_count_with_explicit_branch(self, service, mock_git_network):
        """Test with explicit branch name skips rev-parse"""
        mock_git_network.run_command.return_value = "2\n"

        result = service.count_unpushed_commits(branch="feature", remote="origin")

        assert isinstance(result, ClientSuccess)
        assert result.data == 2
        mock_git_network.run_command.assert_called_once()

    def test_resolves_current_branch_when_none(self, service, mock_git_network):
        """Test with branch=None resolves current branch first"""
        mock_git_network.run_command.side_effect = ["feature-branch\n", "1\n"]

        result = service.count_unpushed_commits(branch=None)

        assert isinstance(result, ClientSuccess)
        assert result.data == 1
        assert mock_git_network.run_command.call_count == 2

    def test_empty_output_returns_zero(self, service, mock_git_network):
        """Test empty rev-list output returns 0"""
        mock_git_network.run_command.return_value = ""

        result = service.count_unpushed_commits(branch="main")

        assert isinstance(result, ClientSuccess)
        assert result.data == 0
