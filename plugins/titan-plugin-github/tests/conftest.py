"""
Pytest configuration and shared fixtures for GitHub plugin tests
"""

import pytest
from unittest.mock import Mock
from titan_plugin_github.models.network.graphql import GraphQLPullRequestReviewThread, GraphQLPullRequestReviewComment, GraphQLUser


@pytest.fixture
def sample_network_user():
    """Create a sample NetworkUser (raw API response model)"""
    from titan_plugin_github.models.network.rest import NetworkUser

    return NetworkUser(
        login="test-user",
        name="Test User",
        email="test@example.com"
    )


@pytest.fixture
def sample_network_review(sample_network_user):
    """Create a sample NetworkReview"""
    from titan_plugin_github.models.network.rest import NetworkReview

    return NetworkReview(
        id=123,
        user=sample_network_user,
        body="Looks good to me!",
        state="APPROVED",
        submitted_at="2025-01-15T10:00:00Z",
        commit_id="abc123def456789"
    )


@pytest.fixture
def sample_network_pr(sample_network_user):
    """Create a sample NetworkPullRequest"""
    from titan_plugin_github.models.network.rest import NetworkPullRequest

    return NetworkPullRequest(
        number=123,
        title="feat: Add new feature",
        body="This PR adds a new feature",
        state="OPEN",
        author=sample_network_user,
        baseRefName="main",
        headRefName="feat/new-feature",
        additions=50,
        deletions=10,
        changedFiles=3,
        mergeable="MERGEABLE",
        isDraft=False,
        createdAt="2025-01-15T10:00:00Z",
        updatedAt="2025-01-15T11:00:00Z",
        mergedAt=None,
        reviews=[],
        labels=[{"name": "feature"}, {"name": "backend"}],
        statusCheckRollup=[],
        reviewDecision="REVIEW_REQUIRED",
        isCrossRepository=False,
        headRepositoryOwnerLogin="test-owner",
    )


@pytest.fixture
def sample_ui_pr():
    """Create a sample UIPullRequest (pre-formatted for display)"""
    from titan_plugin_github.models.view import UIPullRequest

    return UIPullRequest(
        number=123,
        title="feat: Add new feature",
        body="This PR adds a new feature",
        status_icon="🟢",
        state="OPEN",
        author_name="test-user",
        head_ref="feat/new-feature",
        base_ref="main",
        branch_info="feat/new-feature → main",
        stats="+50 -10",
        files_changed=3,
        is_mergeable=True,
        is_draft=False,
        review_summary="No reviews",
        checks_summary="No checks",
        review_status_summary="review required",
        labels=["feature", "backend"],
        formatted_created_at="15/01/2025 10:00:00",
        formatted_updated_at="15/01/2025 11:00:00",
        is_cross_repository=False,
        head_repository_owner="test-owner",
    )


@pytest.fixture
def sample_ui_review():
    """Create a sample UIReview"""
    from titan_plugin_github.models.view import UIReview

    return UIReview(
        id=123,
        author_name="Test User",
        body="Looks good to me!",
        state_icon="🟢",
        state="APPROVED",
        formatted_submitted_at="15/01/2025 10:00:00",
        commit_id_short="abc123d"
    )


@pytest.fixture
def sample_network_issue(sample_network_user):
    """Create a sample NetworkIssue"""
    from titan_plugin_github.models.network.rest import NetworkIssue

    return NetworkIssue(
        number=456,
        title="bug: Fix login issue",
        body="Users cannot login",
        state="open",
        author=sample_network_user,
        labels=[{"name": "bug"}, {"name": "high-priority"}],
        createdAt="2025-01-15T10:00:00Z",
        updatedAt="2025-01-15T11:00:00Z"
    )


@pytest.fixture
def sample_ui_issue():
    """Create a sample UIIssue"""
    from titan_plugin_github.models.view import UIIssue

    return UIIssue(
        number=456,
        title="bug: Fix login issue",
        body="Users cannot login",
        status_icon="🟢",
        state="OPEN",
        author_name="test-user",
        labels=["bug", "high-priority"],
        formatted_created_at="15/01/2025 10:00:00",
        formatted_updated_at="15/01/2025 11:00:00"
    )


@pytest.fixture
def mock_gh_network():
    """Create a mock GHNetwork for testing services"""
    network = Mock()
    network.repo_owner = "test-owner"
    network.repo_name = "test-repo"
    network.get_repo_arg = Mock(return_value=["--repo", "test-owner/test-repo"])
    network.get_repo_string = Mock(return_value="test-owner/test-repo")
    return network


@pytest.fixture
def mock_graphql_network():
    """Create a mock GraphQLNetwork for testing services"""
    network = Mock()
    return network


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client for testing steps"""
    from titan_cli.core.result import ClientSuccess

    client = Mock()
    client.repo_owner = "test-owner"
    client.repo_name = "test-repo"

    # Mock methods to return ClientSuccess by default
    client.reply_to_comment = Mock(return_value=ClientSuccess(data=None, message="Comment posted"))
    client.resolve_review_thread = Mock(return_value=ClientSuccess(data=None, message="Thread resolved"))
    client.request_pr_review = Mock(return_value=ClientSuccess(data=None, message="Review requested"))

    return client


@pytest.fixture
def mock_git_client():
    """Create a mock Git client for testing"""
    from titan_cli.core.result import ClientSuccess

    client = Mock()
    client.main_branch = "main"

    client.create_worktree = Mock(return_value=ClientSuccess(data=None, message="Created"))
    client.remove_worktree = Mock(return_value=ClientSuccess(data=None, message="Removed"))
    client.prune_worktrees = Mock(return_value=ClientSuccess(data=None, message="Pruned"))
    client.commit_in_worktree = Mock(return_value=ClientSuccess(
        data="abc123def456789abc123def456789abc1234567", message="Committed"
    ))
    client.push_from_worktree = Mock(return_value=ClientSuccess(data=None, message="Pushed"))

    return client


@pytest.fixture
def mock_ai_client():
    """Create a mock AI client for testing"""
    client = Mock()
    client.is_available = Mock(return_value=True)
    client.execute = Mock(return_value="AI response")
    return client


@pytest.fixture
def sample_github_user():
    """Create a sample GraphQL GitHub user"""
    return GraphQLUser(
        login="test-user",
        name="Test User"
    )


@pytest.fixture
def sample_review_comment(sample_github_user):
    """Create a sample GraphQL review comment"""
    return GraphQLPullRequestReviewComment(
        databaseId=1001,
        body="This needs to be fixed",
        author=sample_github_user,
        createdAt="2025-01-15T10:00:00Z",
        updatedAt="2025-01-15T10:00:00Z",
        path="src/main.py",
        line=42,
        diffHunk="@@ -40,7 +40,7 @@\n def main():\n-    old_code()\n+    new_code()\n"
    )


@pytest.fixture
def sample_pr_thread(sample_review_comment, sample_github_user):
    """Create a sample GraphQL PR review thread"""
    reply = GraphQLPullRequestReviewComment(
        databaseId=1002,
        body="I'll fix this",
        author=sample_github_user,
        createdAt="2025-01-15T11:00:00Z",
        updatedAt="2025-01-15T11:00:00Z",
        path="src/main.py",
        line=42,
        diffHunk=None
    )

    return GraphQLPullRequestReviewThread(
        id="thread_123",
        isResolved=False,
        isOutdated=False,
        path="src/main.py",
        comments=[sample_review_comment, reply]
    )


@pytest.fixture
def sample_pr_threads(sample_pr_thread):
    """Create a list of sample PR threads"""
    return [sample_pr_thread]


@pytest.fixture
def sample_ui_comment_thread(sample_pr_thread):
    """Create a sample UI comment thread (view model)"""
    from titan_plugin_github.models.view import UICommentThread
    return UICommentThread.from_review_thread(sample_pr_thread)


@pytest.fixture
def client_success():
    """Factory for creating ClientSuccess instances"""
    from titan_cli.core.result import ClientSuccess

    def _create(data, message="Success"):
        return ClientSuccess(data=data, message=message)

    return _create


@pytest.fixture
def client_error():
    """Factory for creating ClientError instances"""
    from titan_cli.core.result import ClientError

    def _create(error_message, error_code=None):
        return ClientError(
            error_message=error_message,
            error_code=error_code
        )

    return _create


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers",
        "unit: marks tests as unit tests (use mocks, no external dependencies)"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require real APIs)"
    )
