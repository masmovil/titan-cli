# plugins/titan-plugin-git/tests/test_git_plugin.py
import pytest
from unittest.mock import MagicMock
from titan_cli.engine import WorkflowContext, is_success, is_error
from titan_plugin_git.steps.status_step import get_git_status_step
from titan_plugin_git.steps.commit_step import create_git_commit_step
from titan_plugin_git.clients.git_client import GitClient
from titan_plugin_git.models import GitStatus
from titan_plugin_git.exceptions import GitCommandError

def test_get_git_status_step_success():
    """
    Test that get_git_status_step successfully retrieves git status.
    """
    # 1. Arrange
    mock_git_client = MagicMock(spec=GitClient)
    mock_status = GitStatus(
        branch="main",
        is_clean=True,
        modified_files=[],
        untracked_files=[],
        staged_files=[],
        ahead=0,
        behind=0
    )
    mock_git_client.get_status.return_value = mock_status
    
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = mock_git_client
    
    # 2. Act
    result = get_git_status_step(mock_context)
    
    # 3. Assert
    assert is_success(result)
    assert result.metadata['git_status'] == mock_status
    mock_git_client.get_status.assert_called_once()


def test_get_git_status_step_no_client():
    """
    Test that get_git_status_step returns an Error if no git client is available.
    """
    # 1. Arrange
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = None
    
    # 2. Act
    result = get_git_status_step(mock_context)
    
    # 3. Assert
    assert is_error(result)
    assert "Git client is not available" in result.message


def test_get_git_status_step_client_error():
    """
    Test that get_git_status_step returns an Error if the client raises an exception.
    """
    # 1. Arrange
    mock_git_client = MagicMock(spec=GitClient)
    mock_git_client.get_status.side_effect = Exception("A git error occurred")
    
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = mock_git_client
    
    # 2. Act
    result = get_git_status_step(mock_context)
    
    # 3. Assert
    assert is_error(result)
    assert "Failed to get git status" in result.message
    assert "A git error occurred" in result.message


def test_create_git_commit_step_success():
    """
    Test that create_git_commit_step successfully creates a commit.
    """
    # 1. Arrange
    mock_git_client = MagicMock(spec=GitClient)
    expected_commit_hash = "abcdef123456"
    mock_git_client.commit.return_value = expected_commit_hash
    
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = mock_git_client
    mock_context.get.side_effect = lambda key, default=None: {
        'commit_message': "Test commit message",
        'all_files': True
    }.get(key, default)
    
    # 2. Act
    result = create_git_commit_step(mock_context)
    
    # 3. Assert
    assert is_success(result)
    assert result.message == f"Commit created successfully: {expected_commit_hash}"
    assert result.metadata['commit_hash'] == expected_commit_hash
    mock_git_client.commit.assert_called_once_with(message="Test commit message", all=True)


def test_create_git_commit_step_no_client():
    """
    Test that create_git_commit_step returns an Error if no git client is available.
    """
    # 1. Arrange
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = None
    
    # 2. Act
    result = create_git_commit_step(mock_context)
    
    # 3. Assert
    assert is_error(result)
    assert "Git client is not available" in result.message


def test_create_git_commit_step_missing_message():
    """
    Test that create_git_commit_step returns an Error if commit message is missing.
    """
    # 1. Arrange
    mock_git_client = MagicMock(spec=GitClient)
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = mock_git_client
    mock_context.get.return_value = None # Simulate no commit message
    
    # 2. Act
    result = create_git_commit_step(mock_context)
    
    # 3. Assert
    assert is_error(result)
    assert "Commit message is required" in result.message
    mock_git_client.commit.assert_not_called()


def test_create_git_commit_step_client_error():
    """
    Test that create_git_commit_step returns an Error if the client's commit operation fails.
    """
    # 1. Arrange
    mock_git_client = MagicMock(spec=GitClient)
    mock_git_client.commit.side_effect = GitCommandError("Commit command failed")
    
    mock_context = MagicMock(spec=WorkflowContext)
    mock_context.git = mock_git_client
    mock_context.get.side_effect = lambda key, default=None: {
        'commit_message': "Test commit message",
        'all_files': False
    }.get(key, default)
    
    # 2. Act
    result = create_git_commit_step(mock_context)
    
    # 3. Assert
    assert is_error(result)
    assert "Git command failed during commit" in result.message
    assert "Commit command failed" in result.message
