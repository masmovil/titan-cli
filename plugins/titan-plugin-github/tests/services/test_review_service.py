"""
Unit tests for ReviewService

Tests the Service layer which transforms Network models to UI models
and wraps results in ClientResult.
"""

import pytest
import json
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_github.clients.services import ReviewService
from titan_plugin_github.exceptions import GitHubAPIError


@pytest.fixture
def review_service(mock_gh_network, mock_graphql_network):
    """Create a ReviewService instance"""
    return ReviewService(mock_gh_network, mock_graphql_network)


@pytest.fixture
def sample_review_json():
    """Sample review response from GitHub API"""
    return {
        "id": 123,
        "user": {
            "login": "test-user",
            "name": "Test User",
            "email": "test@example.com"
        },
        "body": "Looks good to me!",
        "state": "APPROVED",
        "submitted_at": "2025-01-15T10:00:00Z",
        "commit_id": "abc123def456789"
    }


@pytest.fixture
def sample_thread_graphql_response():
    """Sample GraphQL response for review threads"""
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "thread_123",
                                "isResolved": False,
                                "isOutdated": False,
                                "path": "src/main.py",
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 1001,
                                            "body": "This needs to be fixed",
                                            "author": {
                                                "login": "reviewer",
                                                "name": "Reviewer Name"
                                            },
                                            "createdAt": "2025-01-15T10:00:00Z",
                                            "updatedAt": "2025-01-15T10:00:00Z",
                                            "path": "src/main.py",
                                            "line": 42,
                                            "originalLine": None,
                                            "diffHunk": "@@ -40,7 +40,7 @@"
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
    }


def test_get_pr_reviews_success(review_service, mock_gh_network, sample_review_json):
    """Test successful retrieval of PR reviews"""
    # Setup mock
    reviews_json = [sample_review_json]
    mock_gh_network.run_command.return_value = json.dumps(reviews_json)

    # Call service
    result = review_service.get_pr_reviews(123)

    # Assertions
    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 1
    assert result.data[0].id == 123
    assert result.data[0].author_name == "Test User"
    assert result.data[0].state == "APPROVED"
    assert result.data[0].state_icon == "🟢"
    assert result.data[0].commit_id_short == "abc123d"

    # Verify network call
    call_args = mock_gh_network.run_command.call_args[0][0]
    assert "api" in call_args
    assert "/pulls/123/reviews" in " ".join(call_args)


def test_get_pr_reviews_multiple(review_service, mock_gh_network, sample_review_json):
    """Test retrieving multiple reviews"""
    # Setup mock with multiple reviews
    reviews_json = [
        sample_review_json,
        {
            "id": 124,
            "user": {"login": "user2", "name": "User Two"},
            "body": "Needs changes",
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2025-01-15T11:00:00Z",
            "commit_id": "def456abc123"
        }
    ]
    mock_gh_network.run_command.return_value = json.dumps(reviews_json)

    result = review_service.get_pr_reviews(123)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 2
    assert result.data[0].state_icon == "🟢"  # APPROVED
    assert result.data[1].state_icon == "🔴"  # CHANGES_REQUESTED


def test_get_pr_reviews_empty(review_service, mock_gh_network):
    """Test getting reviews when none exist"""
    # Setup mock to return empty array
    mock_gh_network.run_command.return_value = "[]"

    result = review_service.get_pr_reviews(123)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 0
    assert "0 reviews" in result.message


def test_get_pr_reviews_api_error(review_service, mock_gh_network):
    """Test getting reviews when API fails"""
    # Setup mock to raise API error
    mock_gh_network.run_command.side_effect = GitHubAPIError("PR not found")

    result = review_service.get_pr_reviews(999)

    assert isinstance(result, ClientError)
    assert result.error_code == "API_ERROR"


def test_get_pr_review_threads_success(review_service, mock_graphql_network, sample_thread_graphql_response):
    """Test successful retrieval of review threads"""
    # Setup mock
    mock_graphql_network.run_query.return_value = sample_thread_graphql_response

    # Call service
    result = review_service.get_pr_review_threads(123)

    # Assertions
    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 1
    assert result.data[0].thread_id == "thread_123"
    assert result.data[0].is_resolved is False
    assert result.data[0].main_comment.body == "This needs to be fixed"

    # Verify GraphQL query was called
    assert mock_graphql_network.run_query.called


def test_get_pr_review_threads_filter_resolved(review_service, mock_graphql_network):
    """Test filtering out resolved threads"""
    # Setup mock with resolved and unresolved threads
    response = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "thread_1",
                                "isResolved": True,
                                "isOutdated": False,
                                "path": "src/a.py",
                                "comments": {"nodes": []}
                            },
                            {
                                "id": "thread_2",
                                "isResolved": False,
                                "isOutdated": False,
                                "path": "src/b.py",
                                "comments": {"nodes": []}
                            }
                        ]
                    }
                }
            }
        }
    }
    mock_graphql_network.run_query.return_value = response

    # Call with include_resolved=False
    result = review_service.get_pr_review_threads(123, include_resolved=False)

    # Should only return unresolved thread
    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 1
    assert result.data[0].thread_id == "thread_2"


def test_get_pr_review_threads_empty(review_service, mock_graphql_network):
    """Test getting threads when none exist"""
    # Setup mock with empty threads
    response = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": []
                    }
                }
            }
        }
    }
    mock_graphql_network.run_query.return_value = response

    result = review_service.get_pr_review_threads(123)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 0


def test_resolve_review_thread_success(review_service, mock_graphql_network):
    """Test successful thread resolution"""
    # Setup mock
    mock_graphql_network.run_mutation.return_value = {"data": {}}

    result = review_service.resolve_review_thread("thread_123")

    assert isinstance(result, ClientSuccess)
    assert result.message == "Review thread resolved"

    # Verify mutation was called
    assert mock_graphql_network.run_mutation.called


def test_resolve_review_thread_api_error(review_service, mock_graphql_network):
    """Test resolving thread when API fails"""
    # Setup mock to raise API error
    mock_graphql_network.run_mutation.side_effect = GitHubAPIError("Thread not found")

    result = review_service.resolve_review_thread("invalid_thread")

    assert isinstance(result, ClientError)
    assert result.error_code == "API_ERROR"


def test_create_draft_review_success(review_service, mock_gh_network):
    """Test successful draft review creation via GHNetwork (not raw subprocess)."""
    payload = {
        "commit_id": "abc123",
        "body": "Review body",
        "event": "COMMENT",
        "comments": []
    }
    mock_gh_network.run_command.return_value = json.dumps({"id": 42})
    mock_gh_network.get_repo_string.return_value = "owner/repo"

    result = review_service.create_draft_review(pr_number=1, payload=payload)

    assert isinstance(result, ClientSuccess)
    assert result.data == 42

    # Verify it went through GHNetwork, not raw subprocess
    call_args = mock_gh_network.run_command.call_args
    args = call_args[0][0]
    assert "--method" in args
    assert "POST" in args
    assert "/pulls/1/reviews" in " ".join(args)
    # Payload passed as stdin_input, not via subprocess directly
    assert call_args[1].get("stdin_input") or call_args[0][1]


def test_create_draft_review_parse_error(review_service, mock_gh_network):
    """Test handling invalid JSON response from gh CLI."""
    mock_gh_network.run_command.return_value = "not-valid-json"
    mock_gh_network.get_repo_string.return_value = "owner/repo"

    result = review_service.create_draft_review(pr_number=1, payload={})

    assert isinstance(result, ClientError)
    assert result.error_code == "PARSE_ERROR"


def test_create_draft_review_api_error(review_service, mock_gh_network):
    """Test handling gh CLI failure during draft review creation."""
    mock_gh_network.run_command.side_effect = GitHubAPIError("Unauthorized")
    mock_gh_network.get_repo_string.return_value = "owner/repo"

    result = review_service.create_draft_review(pr_number=1, payload={})

    assert isinstance(result, ClientError)
    assert result.error_code == "API_ERROR"


def test_submit_review_pending_review_exists(review_service, mock_gh_network):
    """Test specific pending-review conflict is mapped to structured error."""
    mock_gh_network.get_repo_string.return_value = "owner/repo"
    mock_gh_network.run_command.side_effect = GitHubAPIError(
        "gh: Unprocessable Entity (HTTP 422) | {\"errors\":[\"User can only have one pending review per pull request\"]}"
    )

    result = review_service.submit_review(1, None, "COMMENT")

    assert isinstance(result, ClientError)
    assert result.error_code == "PENDING_REVIEW_EXISTS"
    assert "review in progress" in result.error_message.lower()
    assert result.log_level == "warning"


# ---------------------------------------------------------------------------
# get_pr_general_comments: issue comments + submitted review bodies
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_general_comments_graphql_response():
    """Issue comments plus reviews: one with findings, one pending, one empty approval."""
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "comments": {
                        "nodes": [
                            {
                                "databaseId": 2001,
                                "body": "General question about the approach",
                                "author": {"login": "human", "name": "Human"},
                                "createdAt": "2026-07-31T06:00:00Z",
                                "updatedAt": "2026-07-31T06:00:00Z",
                            }
                        ]
                    },
                    "reviews": {
                        "nodes": [
                            {
                                "databaseId": 3001,
                                "body": "**src/foo.py** (line 866):\nFinding text",
                                "state": "COMMENTED",
                                "author": {"login": "titan", "name": "Titan"},
                                "createdAt": "2026-07-31T06:11:00Z",
                                "updatedAt": "2026-07-31T06:11:00Z",
                            },
                            {
                                "databaseId": 3002,
                                "body": "",
                                "state": "APPROVED",
                                "author": {"login": "human", "name": "Human"},
                                "createdAt": "2026-07-31T07:00:00Z",
                                "updatedAt": "2026-07-31T07:00:00Z",
                            },
                            {
                                "databaseId": 3003,
                                "body": "draft notes",
                                "state": "PENDING",
                                "author": {"login": "human", "name": "Human"},
                                "createdAt": None,
                                "updatedAt": None,
                            },
                        ]
                    },
                }
            }
        }
    }


def test_get_pr_general_comments_includes_submitted_review_bodies(
    review_service, mock_graphql_network, sample_general_comments_graphql_response
):
    """Review bodies are where unanchorable findings end up — the respond
    workflow must see them, not just issue comments."""
    mock_graphql_network.run_query.return_value = sample_general_comments_graphql_response

    result = review_service.get_pr_general_comments(42)

    assert isinstance(result, ClientSuccess)
    bodies = [t.main_comment.body for t in result.data]
    assert "General question about the approach" in bodies
    assert "**src/foo.py** (line 866):\nFinding text" in bodies


def test_get_pr_general_comments_skips_pending_and_empty_reviews(
    review_service, mock_graphql_network, sample_general_comments_graphql_response
):
    mock_graphql_network.run_query.return_value = sample_general_comments_graphql_response

    result = review_service.get_pr_general_comments(42)

    assert isinstance(result, ClientSuccess)
    assert len(result.data) == 2  # 1 issue comment + 1 submitted review with body
    assert all(t.is_general_comment for t in result.data)


def test_get_pr_general_comments_without_reviews_key_still_works(
    review_service, mock_graphql_network
):
    """Defensive: a response missing the reviews connection must not break."""
    mock_graphql_network.run_query.return_value = {
        "data": {"repository": {"pullRequest": {"comments": {"nodes": []}}}}
    }

    result = review_service.get_pr_general_comments(42)

    assert isinstance(result, ClientSuccess)
    assert result.data == []


# ---------------------------------------------------------------------------
# add_issue_comment: body must travel via stdin, not as a literal "-"
# ---------------------------------------------------------------------------


def test_add_issue_comment_reads_body_from_stdin(review_service, mock_gh_network):
    """gh api needs "body=@-" to read the field from stdin — a bare "body=-" is
    taken literally and every general reply gets posted as a one-dash comment
    (live-observed on PR #253, 2026-07-31)."""
    result = review_service.add_issue_comment(42, "Actual reply text")

    assert isinstance(result, ClientSuccess)
    args, kwargs = mock_gh_network.run_command.call_args
    assert "body=@-" in args[0]
    assert "body=-" not in args[0]
    assert kwargs.get("stdin_input") == "Actual reply text"
