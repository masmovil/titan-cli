"""
Unit tests for GitHubClient (Facade)

Tests that the client correctly delegates to services and provides a clean public API.
"""

import pytest
from unittest.mock import Mock, patch
from titan_cli.core.result import ClientSuccess
from titan_plugin_github.clients import GitHubClient


@pytest.fixture
def mock_gh_network():
    """Mock GHNetwork"""
    with patch('titan_plugin_github.clients.github_client.GHNetwork') as mock:
        yield mock.return_value


@pytest.fixture
def mock_graphql_network():
    """Mock GraphQLNetwork"""
    with patch('titan_plugin_github.clients.github_client.GraphQLNetwork') as mock:
        yield mock.return_value


@pytest.fixture
def github_client(mock_gh_network, mock_graphql_network):
    """Create a GitHubClient instance with mocked networks"""
    from titan_cli.core.plugins.models import GitHubPluginConfig

    with patch('titan_plugin_github.clients.github_client.GitClient'):
        config = GitHubPluginConfig(repo_owner="test-owner", repo_name="test-repo")
        return GitHubClient(
            config=config,
            git_client=Mock(),
            repo_owner="test-owner",
            repo_name="test-repo"
        )


def test_client_initialization():
    """Test that client initializes correctly"""
    from titan_cli.core.plugins.models import GitHubPluginConfig

    with patch('titan_plugin_github.clients.github_client.GHNetwork'):
        with patch('titan_plugin_github.clients.github_client.GraphQLNetwork'):
            with patch('titan_plugin_github.clients.github_client.GitClient'):
                config = GitHubPluginConfig(repo_owner="test-owner", repo_name="test-repo")
                client = GitHubClient(
                    config=config,
                    git_client=Mock(),
                    repo_owner="test-owner",
                    repo_name="test-repo"
                )

                assert client.repo_owner == "test-owner"
                assert client.repo_name == "test-repo"
                assert client._gh_network is not None
                assert client._pr_service is not None
                assert client._review_service is not None
                assert client._issue_service is not None
                assert client._team_service is not None
                assert client._release_service is not None


def test_get_pull_request_delegates_to_service(github_client, sample_ui_pr):
    """Test that get_pull_request delegates to PRService"""
    # Mock the service method
    github_client._pr_service.get_pull_request = Mock(
        return_value=ClientSuccess(data=sample_ui_pr, message="Success")
    )

    # Call client method
    result = github_client.get_pull_request(123)

    # Assertions
    assert isinstance(result, ClientSuccess)
    assert result.data.number == 123
    github_client._pr_service.get_pull_request.assert_called_once_with(123)


def test_merge_pr_delegates_to_service(github_client):
    """Test that merge_pr delegates to PRService"""
    from titan_plugin_github.models.view import UIPRMergeResult

    merge_result = UIPRMergeResult(
        merged=True,
        status_icon="✅",
        sha_short="abc123d",
        message="Successfully merged"
    )

    github_client._pr_service.merge_pr = Mock(
        return_value=ClientSuccess(data=merge_result, message="PR merged")
    )

    result = github_client.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is True
    github_client._pr_service.merge_pr.assert_called_once_with(123, "squash", None, None)


def test_create_issue_delegates_to_service(github_client, sample_ui_issue):
    """Test that create_issue delegates to IssueService"""
    github_client._issue_service.create_issue = Mock(
        return_value=ClientSuccess(data=sample_ui_issue, message="Issue created")
    )

    result = github_client.create_issue(
        title="Test Issue",
        body="Description",
        assignees=["user1"],
        labels=["bug"]
    )

    assert isinstance(result, ClientSuccess)
    assert result.data.number == 456
    # Verify service was called with positional arguments
    github_client._issue_service.create_issue.assert_called_once_with(
        "Test Issue",
        "Description",
        ["user1"],
        ["bug"]
    )


def test_list_labels_delegates_to_service(github_client):
    """Test that list_labels delegates to IssueService"""
    github_client._issue_service.list_labels = Mock(
        return_value=ClientSuccess(data=["bug", "feature"], message="Found 2 labels")
    )

    result = github_client.list_labels()

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 2
    github_client._issue_service.list_labels.assert_called_once()


def test_create_release_delegates_to_service(github_client):
    """Test that create_release delegates to ReleaseService"""
    from titan_plugin_github.models.view import UIRelease

    github_client._release_service.create_release = Mock(
        return_value=ClientSuccess(
            data=UIRelease(
                tag_name="0.4.1",
                title="0.4.1",
                url="https://github.com/test-owner/test-repo/releases/tag/0.4.1",
                is_prerelease=False,
            ),
            message="Release created"
        )
    )

    result = github_client.create_release(
        tag_name="0.4.1",
        title="0.4.1",
        notes="Release notes",
        generate_notes=False,
        verify_tag=True,
        prerelease=False,
    )

    assert isinstance(result, ClientSuccess)
    assert result.data.tag_name == "0.4.1"
    assert result.data.url == "https://github.com/test-owner/test-repo/releases/tag/0.4.1"
    github_client._release_service.create_release.assert_called_once_with(
        tag_name="0.4.1",
        title="0.4.1",
        notes="Release notes",
        generate_notes=False,
        verify_tag=True,
        prerelease=False,
    )


def test_get_pr_reviews_delegates_to_service(github_client, sample_ui_review):
    """Test that get_pr_reviews delegates to ReviewService"""
    github_client._review_service.get_pr_reviews = Mock(
        return_value=ClientSuccess(data=[sample_ui_review], message="Found 1 reviews")
    )

    result = github_client.get_pr_reviews(123)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 1
    assert result.data[0].id == 123
    github_client._review_service.get_pr_reviews.assert_called_once_with(123)


def test_get_pr_review_threads_delegates_to_service(github_client, sample_ui_comment_thread):
    """Test that get_pr_review_threads delegates to ReviewService"""
    github_client._review_service.get_pr_review_threads = Mock(
        return_value=ClientSuccess(data=[sample_ui_comment_thread], message="Found 1 threads")
    )

    result = github_client.get_pr_review_threads(123)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 1
    github_client._review_service.get_pr_review_threads.assert_called_once_with(123, True)


def test_resolve_review_thread_delegates_to_service(github_client):
    """Test that resolve_review_thread delegates to ReviewService"""
    github_client._review_service.resolve_review_thread = Mock(
        return_value=ClientSuccess(data=None, message="Thread resolved")
    )

    result = github_client.resolve_review_thread("thread_123")

    assert isinstance(result, ClientSuccess)
    github_client._review_service.resolve_review_thread.assert_called_once_with("thread_123")


def test_get_commit_review_context_delegates_to_service(github_client):
    """Test that commit review context delegates to PRService."""
    from titan_plugin_github.models.review_models import ReferencedCommitContext

    commit_context = ReferencedCommitContext(
        sha="343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
        abbreviated_sha="343e2e9",
        message="remove default state value",
        changed_files=["src/BaseDialog.kt"],
        patch_excerpt="diff --git a/src/BaseDialog.kt b/src/BaseDialog.kt",
    )
    github_client._pr_service.get_commit_review_context = Mock(
        return_value=ClientSuccess(data=commit_context, message="Commit context retrieved")
    )

    result = github_client.get_commit_review_context("343e2e9", max_files=2, max_patch_chars=1200)

    assert isinstance(result, ClientSuccess)
    assert result.data.abbreviated_sha == "343e2e9"
    github_client._pr_service.get_commit_review_context.assert_called_once_with(
        "343e2e9",
        repo_owner=None,
        repo_name=None,
        max_files=2,
        max_patch_chars=1200,
    )
