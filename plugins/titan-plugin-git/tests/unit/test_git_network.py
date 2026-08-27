"""
Unit tests for Git Network Layer
"""

import pytest
from unittest.mock import Mock, patch
from titan_plugin_git.clients.network import GitNetwork
from titan_plugin_git.exceptions import GitClientError, GitCommandError, GitNotRepositoryError


@pytest.mark.unit
class TestGitNetworkInitialization:
    """Test GitNetwork initialization"""

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch.object(GitNetwork, '_check_repository')
    def test_initialization_success(self, mock_check_repo, mock_which):
        """Test successful initialization"""
        mock_which.return_value = '/usr/bin/git'

        network = GitNetwork(repo_path="/tmp/repo")

        assert network.repo_path == "/tmp/repo"
        mock_which.assert_called_once_with("git")
        mock_check_repo.assert_called_once()

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    def test_initialization_git_not_found(self, mock_which):
        """Test initialization fails when git is not installed"""
        mock_which.return_value = None

        with pytest.raises(GitClientError, match="Git CLI"):
            GitNetwork(repo_path="/tmp/repo")

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch.object(GitNetwork, 'run_command')
    def test_initialization_not_a_repository(self, mock_run_command, mock_which):
        """Test initialization fails when not in a git repository"""
        mock_which.return_value = '/usr/bin/git'
        mock_run_command.side_effect = GitCommandError("not a git repository")

        with pytest.raises(GitNotRepositoryError):
            GitNetwork(repo_path="/tmp/not-a-repo")


@pytest.mark.unit
class TestGitNetworkRunCommand:
    """Test GitNetwork.run_command()"""

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_success(self, mock_check_repo, mock_subprocess, mock_which):
        """Test successful command execution"""
        mock_which.return_value = '/usr/bin/git'
        mock_result = Mock()
        mock_result.stdout = 'main\n'
        mock_subprocess.return_value = mock_result

        network = GitNetwork(repo_path="/tmp/repo")
        output = network.run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])

        assert output == "main"
        mock_subprocess.assert_called_once()

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_preserves_leading_status_space(
        self, mock_check_repo, mock_subprocess, mock_which
    ):
        """Test git status output keeps semantic leading spaces."""
        mock_which.return_value = '/usr/bin/git'
        mock_result = Mock()
        mock_result.stdout = ' M app/file.py\n'
        mock_subprocess.return_value = mock_result

        network = GitNetwork(repo_path="/tmp/repo")
        output = network.run_command(["git", "status", "--short"])

        assert output == " M app/file.py"

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_strip_output_false_preserves_trailing_context_line(
        self, mock_check_repo, mock_subprocess, mock_which
    ):
        """A diff whose last hunk ends in an empty context line ends with ' \\n' —
        stripping it leaves the hunk one line short of its @@ header's declared
        count, which desyncs the parser and blocks inline comment placement."""
        mock_which.return_value = '/usr/bin/git'
        mock_result = Mock()
        mock_result.stdout = '@@ -1,2 +1,2 @@\n+code\n \n'
        mock_subprocess.return_value = mock_result

        network = GitNetwork(repo_path="/tmp/repo")
        output = network.run_command(["git", "diff", "a...b"], strip_output=False)

        assert output == '@@ -1,2 +1,2 @@\n+code\n \n'

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_with_custom_cwd(self, mock_check_repo, mock_subprocess, mock_which):
        """Test command execution with custom working directory"""
        mock_which.return_value = '/usr/bin/git'
        mock_result = Mock()
        mock_result.stdout = 'feature\n'
        mock_subprocess.return_value = mock_result

        network = GitNetwork(repo_path="/tmp/repo")
        output = network.run_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd="/tmp/custom"
        )

        assert output == "feature"
        # Verify cwd was passed
        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs['cwd'] == "/tmp/custom"

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_error(self, mock_check_repo, mock_subprocess, mock_which):
        """Test command execution error"""
        mock_which.return_value = '/usr/bin/git'

        import subprocess
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "invalid"],
            stderr="fatal: not a valid command"
        )

        network = GitNetwork(repo_path="/tmp/repo")

        with pytest.raises(GitCommandError, match="failed"):
            network.run_command(["git", "invalid"])

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_not_a_repository_error(self, mock_check_repo, mock_subprocess, mock_which):
        """Test command fails with 'not a git repository' error"""
        mock_which.return_value = '/usr/bin/git'

        import subprocess
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "status"],
            stderr="fatal: not a git repository"
        )

        network = GitNetwork(repo_path="/tmp/repo")

        with pytest.raises(GitNotRepositoryError):
            network.run_command(["git", "status"])

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch('titan_plugin_git.clients.network.git_network.subprocess.run')
    @patch.object(GitNetwork, '_check_repository')
    def test_run_command_check_false(self, mock_check_repo, mock_subprocess, mock_which):
        """Test command execution with check=False"""
        mock_which.return_value = '/usr/bin/git'
        mock_result = Mock()
        mock_result.stdout = ''
        mock_subprocess.return_value = mock_result

        network = GitNetwork(repo_path="/tmp/repo")
        output = network.run_command(["git", "status", "--short"], check=False)

        assert output == ""
        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs['check'] is False


@pytest.mark.unit
class TestGitNetworkGetRepoPath:
    """Test GitNetwork.get_repo_path()"""

    @patch('titan_plugin_git.clients.network.git_network.shutil.which')
    @patch.object(GitNetwork, '_check_repository')
    def test_get_repo_path(self, mock_check_repo, mock_which):
        """Test getting repository path"""
        mock_which.return_value = '/usr/bin/git'

        network = GitNetwork(repo_path="/home/user/project")

        assert network.get_repo_path() == "/home/user/project"
