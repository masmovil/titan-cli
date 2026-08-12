"""
Unit tests for GHNetwork (gh CLI layer)

Tests the Network layer which handles raw gh CLI command execution.
"""

import pytest
import subprocess
from unittest.mock import Mock, patch
from titan_plugin_github.clients.network import GHNetwork
from titan_plugin_github.exceptions import GitHubError, GitHubAuthenticationError, GitHubAPIError


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run to avoid actual gh CLI calls"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock:
        # Mock auth check to succeed by default
        mock.return_value = Mock(returncode=0, stdout="", stderr="")
        yield mock


@pytest.fixture
def gh_network(mock_subprocess):
    """Create a GHNetwork instance for testing"""
    return GHNetwork(repo_owner="test-owner", repo_name="test-repo")


def test_network_initialization(gh_network):
    """Test that GHNetwork initializes correctly"""
    assert gh_network.repo_owner == "test-owner"
    assert gh_network.repo_name == "test-repo"


def test_network_initialization_checks_auth(mock_subprocess):
    """Test that initialization checks gh CLI authentication"""
    # Reset mock to verify auth check call
    mock_subprocess.reset_mock()

    # Create network - should call gh auth status
    GHNetwork(repo_owner="test-owner", repo_name="test-repo")

    # Verify gh auth status was called
    assert mock_subprocess.call_count == 1
    call_args = mock_subprocess.call_args[0][0]
    assert call_args == ["gh", "auth", "status"]


def test_network_initialization_raises_when_not_authenticated():
    """Test that initialization raises error if gh CLI not authenticated"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        # Simulate auth failure
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "auth", "status"],
            stderr="Not authenticated"
        )

        # Should raise authentication error
        with pytest.raises(GitHubAuthenticationError):
            GHNetwork(repo_owner="test-owner", repo_name="test-repo")


def test_run_command_success(gh_network, mock_subprocess):
    """Test successful command execution"""
    # Setup mock
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = '{"number": 123, "title": "Test PR"}\n'
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Run command
    output = gh_network.run_command(["pr", "view", "123", "--json", "number,title"])

    # Assertions
    assert output == '{"number": 123, "title": "Test PR"}'

    # Verify command was called correctly
    call_args = mock_subprocess.call_args
    assert call_args[0][0] == ["gh", "pr", "view", "123", "--json", "number,title"]
    assert call_args[1]["capture_output"] is True
    assert call_args[1]["text"] is True
    assert call_args[1]["check"] is True


def test_run_command_strip_output_false_preserves_trailing_context_line(gh_network, mock_subprocess):
    """A diff whose last hunk ends in an empty context line ends with ' \\n' —
    stripping it leaves the hunk one line short of its @@ header's declared
    count, which desyncs the parser and blocks inline comment placement."""
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = '@@ -1,2 +1,2 @@\n+code\n \n'
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    output = gh_network.run_command(["pr", "diff", "123"], strip_output=False)

    assert output == '@@ -1,2 +1,2 @@\n+code\n \n'


def test_run_command_with_stdin(gh_network, mock_subprocess):
    """Test command execution with stdin input"""
    # Setup mock
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "https://github.com/test-owner/test-repo/issues/123\n"
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Run command with stdin
    stdin_data = "This is a multiline\nissue description"
    output = gh_network.run_command(
        ["issue", "create", "--title", "Test Issue", "--body", "-"],
        stdin_input=stdin_data
    )

    # Assertions
    assert output == "https://github.com/test-owner/test-repo/issues/123"

    # Verify stdin was passed
    call_args = mock_subprocess.call_args
    assert call_args[1]["input"] == stdin_data


def test_run_command_api_error(gh_network):
    """Test command execution when gh CLI returns error"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        # Simulate API error
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "pr", "view", "999"],
            stderr="pull request not found"
        )

        # Should raise GitHubAPIError
        with pytest.raises(GitHubAPIError) as exc_info:
            gh_network.run_command(["pr", "view", "999"])

        assert "pull request not found" in str(exc_info.value).lower()


def test_run_command_api_error_logs_with_custom_logger(gh_network):
    """API failures should be logged via the custom structured logger."""
    gh_network._logger = Mock()

    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "pr", "create", "--body", "secret body"],
            stderr="GraphQL: Something went wrong",
        )

        with pytest.raises(GitHubAPIError):
            gh_network.run_command(["pr", "create", "--body", "secret body"])

    gh_network._logger.error.assert_called_once()
    event_name = gh_network._logger.error.call_args.args[0]
    event_fields = gh_network._logger.error.call_args.kwargs

    assert event_name == "gh_command_failed"
    assert event_fields["subcommand"] == "pr"
    assert event_fields["action"] == "create"
    assert event_fields["exit_code"] == 1
    assert isinstance(event_fields["duration"], float)


def test_run_command_api_error_preserves_stdout_and_stderr(gh_network):
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "api", "/repos/foo/bar/pulls/1/reviews"],
            stderr='gh: Unprocessable Entity (HTTP 422)',
            output='{"message":"Validation Failed","errors":[{"field":"line"}]}'
        )

        with pytest.raises(GitHubAPIError) as exc_info:
            gh_network.run_command(["api", "/repos/foo/bar/pulls/1/reviews"])

    exc = exc_info.value
    assert exc.exit_code == 1
    assert "Validation Failed" in str(exc)
    assert exc.stderr == 'gh: Unprocessable Entity (HTTP 422)'
    assert '"field":"line"' in exc.stdout


def test_run_command_cli_not_found(gh_network):
    """Test command execution when gh CLI is not installed"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        # Simulate FileNotFoundError (gh not found)
        mock_run.side_effect = FileNotFoundError("gh command not found")

        # Should raise GitHubError
        with pytest.raises(GitHubError) as exc_info:
            gh_network.run_command(["pr", "list"])

        assert "not found" in str(exc_info.value).lower() or "cli" in str(exc_info.value).lower()


def test_run_command_unexpected_error(gh_network):
    """Test command execution with unexpected error"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        # Simulate unexpected exception
        mock_run.side_effect = RuntimeError("Unexpected runtime error")

        # Should raise GitHubError
        with pytest.raises(GitHubError):
            gh_network.run_command(["pr", "list"])


def test_get_repo_arg(gh_network):
    """Test that repo argument is constructed correctly"""
    repo_arg = gh_network.get_repo_arg()

    assert repo_arg == ["--repo", "test-owner/test-repo"]


def test_get_repo_arg_when_no_repo():
    """Test that repo argument is empty when no repo configured"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run'):
        network = GHNetwork(repo_owner="", repo_name="")
        repo_arg = network.get_repo_arg()

        assert repo_arg == []


def test_get_repo_string(gh_network):
    """Test that repo string is formatted correctly"""
    repo_string = gh_network.get_repo_string()

    assert repo_string == "test-owner/test-repo"


def test_run_command_strips_whitespace(gh_network, mock_subprocess):
    """Test that command output is stripped of whitespace"""
    # Setup mock with extra whitespace
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "\n\n  some output  \n\n"
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Run command
    output = gh_network.run_command(["pr", "view", "123"])

    # Should be stripped
    assert output == "some output"


def test_run_command_with_empty_stderr(gh_network):
    """Test command error handling when stderr is empty"""
    with patch('titan_plugin_github.clients.network.gh_network.subprocess.run') as mock_run:
        # Simulate error with empty stderr
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "pr", "view", "123"]
        )
        error.stderr = None
        mock_run.side_effect = error

        # Should still raise GitHubAPIError
        with pytest.raises(GitHubAPIError):
            gh_network.run_command(["pr", "view", "123"])
