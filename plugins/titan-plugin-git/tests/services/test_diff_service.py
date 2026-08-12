"""
Unit tests for Diff Service
"""

import pytest
from unittest.mock import Mock
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_git.clients.services.diff_service import DiffService
from titan_plugin_git.exceptions import GitCommandError


@pytest.fixture
def mock_git_network():
    """Mock GitNetwork instance"""
    return Mock()


@pytest.fixture
def service(mock_git_network):
    return DiffService(mock_git_network, default_remote="origin")


@pytest.mark.unit
class TestDiffServiceGetDiff:
    """Test DiffService.get_diff()"""

    def test_returns_diff_output(self, service, mock_git_network):
        """Test returns raw diff between two refs"""
        mock_git_network.run_command.return_value = "diff --git a/foo.py b/foo.py\n..."

        result = service.get_diff("main", "HEAD")

        assert isinstance(result, ClientSuccess)
        assert "diff" in result.data
        mock_git_network.run_command.assert_called_once_with(
            ["git", "diff", "main...HEAD"], check=False, strip_output=False
        )

    def test_uses_head_as_default(self, service, mock_git_network):
        """Test head_ref defaults to HEAD"""
        mock_git_network.run_command.return_value = ""

        service.get_diff("develop")

        args = mock_git_network.run_command.call_args.args[0]
        assert "develop...HEAD" in args

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("bad revision")

        result = service.get_diff("bad-ref")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetUncommittedDiff:
    """Test DiffService.get_uncommitted_diff()"""

    def test_runs_intent_to_add_then_diff(self, service, mock_git_network):
        """Test runs git add --intent-to-add before diff HEAD"""
        mock_git_network.run_command.side_effect = ["", "diff output"]

        result = service.get_uncommitted_diff()

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--intent-to-add", "."] in calls
        assert ["git", "diff", "HEAD"] in calls

    def test_returns_diff_output(self, service, mock_git_network):
        """Test returns diff output from second command"""
        mock_git_network.run_command.side_effect = ["", "some diff content"]

        result = service.get_uncommitted_diff()

        assert isinstance(result, ClientSuccess)
        assert result.data == "some diff content"

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("not a repo")

        result = service.get_uncommitted_diff()

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetUncommittedDiffForFiles:
    """Test DiffService.get_uncommitted_diff_for_files()"""

    def test_runs_intent_to_add_and_diff_for_selected_files(self, service, mock_git_network):
        """Test selected files are passed through both git commands"""
        mock_git_network.run_command.side_effect = ["", "filtered diff"]

        result = service.get_uncommitted_diff_for_files(["src/main.py", "README.md"])

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--intent-to-add", "--", "src/main.py", "README.md"] in calls
        assert ["git", "diff", "HEAD", "--", "src/main.py", "README.md"] in calls

    def test_falls_back_to_full_uncommitted_diff_when_file_list_empty(self, service, mock_git_network):
        """Test empty file list reuses the existing full diff behavior"""
        mock_git_network.run_command.side_effect = ["", "full diff"]

        result = service.get_uncommitted_diff_for_files([])

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--intent-to-add", "."] in calls
        assert ["git", "diff", "HEAD"] in calls

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("not a repo")

        result = service.get_uncommitted_diff_for_files(["src/main.py"])

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetStagedDiff:
    """Test DiffService.get_staged_diff()"""

    def test_runs_diff_cached(self, service, mock_git_network):
        """Test uses --cached flag for staged diff"""
        mock_git_network.run_command.return_value = "staged diff"

        result = service.get_staged_diff()

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "diff", "--cached"], check=False, strip_output=False
        )

    def test_empty_staged_returns_empty_string(self, service, mock_git_network):
        """Test empty staged area returns empty string"""
        mock_git_network.run_command.return_value = ""

        result = service.get_staged_diff()

        assert isinstance(result, ClientSuccess)
        assert result.data == ""

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("error")

        result = service.get_staged_diff()

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetUnstagedDiff:
    """Test DiffService.get_unstaged_diff()"""

    def test_runs_plain_diff(self, service, mock_git_network):
        """Test uses plain git diff for unstaged changes"""
        mock_git_network.run_command.return_value = "unstaged diff"

        result = service.get_unstaged_diff()

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "diff"], check=False, strip_output=False
        )

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("error")

        result = service.get_unstaged_diff()

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetFileDiff:
    """Test DiffService.get_file_diff()"""

    def test_returns_diff_for_specific_file(self, service, mock_git_network):
        """Test passes file path to git diff"""
        mock_git_network.run_command.return_value = "file diff"

        result = service.get_file_diff("src/main.py")

        assert isinstance(result, ClientSuccess)
        mock_git_network.run_command.assert_called_once_with(
            ["git", "diff", "HEAD", "--", "src/main.py"], check=False, strip_output=False
        )

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("path not found")

        result = service.get_file_diff("missing.py")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetBranchDiff:
    """Test DiffService.get_branch_diff()"""

    def test_uses_remote_prefix_for_base(self, service, mock_git_network):
        """Test prepends default_remote to base branch"""
        mock_git_network.run_command.return_value = "branch diff"

        result = service.get_branch_diff("main", "feature")

        assert isinstance(result, ClientSuccess)
        args = mock_git_network.run_command.call_args.args[0]
        assert "origin/main...feature" in args

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("unknown branch")

        result = service.get_branch_diff("main", "feature")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetBranchNumstat:
    """Test DiffService.get_branch_numstat()"""

    def test_parses_numstat_lines(self, service, mock_git_network):
        """Test parses add/del/path triplets into UIFileChurn entries"""
        mock_git_network.run_command.return_value = (
            "120\t5\tsrc/app/main.py\n"
            "0\t452\tsrc/old/removed.py\n"
        )

        result = service.get_branch_numstat("main", "feature")

        assert isinstance(result, ClientSuccess)
        assert [(c.path, c.additions, c.deletions) for c in result.data] == [
            ("src/app/main.py", 120, 5),
            ("src/old/removed.py", 0, 452),
        ]
        args = mock_git_network.run_command.call_args.args[0]
        assert "--numstat" in args
        assert "--no-renames" in args
        assert "origin/main...feature" in args

    def test_marks_binary_files(self, service, mock_git_network):
        """Test binary files ('-' counters) come back flagged with zero counts"""
        mock_git_network.run_command.return_value = "-\t-\tassets/logo.png\n10\t2\tsrc/a.py"

        result = service.get_branch_numstat("main", "feature")

        assert isinstance(result, ClientSuccess)
        binary = result.data[0]
        assert binary.path == "assets/logo.png"
        assert binary.is_binary is True
        assert binary.additions == 0 and binary.deletions == 0
        assert result.data[1].is_binary is False

    def test_uses_remote_prefix_for_both_branches_when_use_remote(self, service, mock_git_network):
        """Test use_remote=True prefixes both refs with the default remote"""
        mock_git_network.run_command.return_value = ""

        service.get_branch_numstat("main", "feature", use_remote=True)

        args = mock_git_network.run_command.call_args.args[0]
        assert "origin/main...origin/feature" in args

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("unknown branch")

        result = service.get_branch_numstat("main", "feature")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetChangedFiles:
    """Test DiffService.get_changed_files()"""

    def test_parses_paths_and_uses_refs_verbatim(self, service, mock_git_network):
        """Test one path per line, refs passed without remote prefixing"""
        mock_git_network.run_command.return_value = "src/a.py\nsrc/b.py\n"

        result = service.get_changed_files("22aa7462", "4a999bc6")

        assert isinstance(result, ClientSuccess)
        assert result.data == ["src/a.py", "src/b.py"]
        args = mock_git_network.run_command.call_args.args[0]
        assert "--name-only" in args
        assert "--no-renames" in args
        assert "22aa7462" in args and "4a999bc6" in args
        assert not any(a.startswith("origin/22aa") for a in args)

    def test_empty_diff_returns_empty_list(self, service, mock_git_network):
        """Test identical refs produce an empty list, not an error"""
        mock_git_network.run_command.return_value = ""

        result = service.get_changed_files("abc", "abc")

        assert isinstance(result, ClientSuccess)
        assert result.data == []

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("bad object")

        result = service.get_changed_files("abc", "def")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetDiffStat:
    """Test DiffService.get_diff_stat()"""

    def test_uses_stat_300_flag(self, service, mock_git_network):
        """Test uses --stat=300 to prevent path truncation"""
        mock_git_network.run_command.return_value = "2 files changed"

        result = service.get_diff_stat("main", "HEAD")

        assert isinstance(result, ClientSuccess)
        args = mock_git_network.run_command.call_args.args[0]
        assert "--stat=300" in args
        assert "main...HEAD" in args

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("bad ref")

        result = service.get_diff_stat("bad-ref")

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"


@pytest.mark.unit
class TestDiffServiceGetUncommittedDiffStat:
    """Test DiffService.get_uncommitted_diff_stat()"""

    def test_runs_intent_to_add_then_stat(self, service, mock_git_network):
        """Test runs intent-to-add then diff --stat HEAD"""
        mock_git_network.run_command.side_effect = ["", "3 files changed"]

        result = service.get_uncommitted_diff_stat()

        assert isinstance(result, ClientSuccess)
        calls = [c.args[0] for c in mock_git_network.run_command.call_args_list]
        assert ["git", "add", "--intent-to-add", "."] in calls
        stat_call = next(c for c in calls if "--stat=300" in c)
        assert "HEAD" in stat_call

    def test_error_returns_client_error(self, service, mock_git_network):
        """Test git error returns ClientError"""
        mock_git_network.run_command.side_effect = GitCommandError("not a repo")

        result = service.get_uncommitted_diff_stat()

        assert isinstance(result, ClientError)
        assert result.error_code == "DIFF_ERROR"
