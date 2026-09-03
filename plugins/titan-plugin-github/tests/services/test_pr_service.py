"""
Unit tests for PRService

Tests the Service layer which transforms Network models to UI models
and wraps results in ClientResult.
"""

import pytest
import json
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_github.clients.services import PRService
from titan_plugin_github.exceptions import GitHubAPIError


@pytest.fixture
def pr_service(mock_gh_network):
    """Create a PRService instance"""
    return PRService(mock_gh_network)


@pytest.fixture
def queue_pr_service(mock_gh_network, mock_graphql_network):
    """Create a PRService instance able to read merge queue state (GraphQL)"""
    return PRService(mock_gh_network, mock_graphql_network)


def merge_queue_response(
    *,
    enabled: bool,
    in_queue: bool = False,
    state: str = "OPEN",
    position: int = None,
    entry_state: str = None,
):
    """Build a GraphQL response for the merge queue query"""
    entry = None
    if in_queue:
        entry = {"position": position, "state": entry_state}

    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "state": state,
                    "isMergeQueueEnabled": enabled,
                    "isInMergeQueue": in_queue,
                    "mergeQueueEntry": entry,
                }
            }
        }
    }


@pytest.fixture
def sample_pr_json():
    """Sample PR response from gh CLI"""
    return {
        "number": 123,
        "title": "feat: Add new feature",
        "body": "This PR adds a new feature",
        "state": "OPEN",
        "author": {
            "login": "test-user",
            "name": "Test User",
            "email": "test@example.com"
        },
        "baseRefName": "main",
        "headRefName": "feat/new-feature",
        "additions": 50,
        "deletions": 10,
        "changedFiles": 3,
        "mergeable": "MERGEABLE",
        "isDraft": False,
        "createdAt": "2025-01-15T10:00:00Z",
        "updatedAt": "2025-01-15T11:00:00Z",
        "mergedAt": None,
        "reviews": [],
        "labels": [{"name": "feature"}, {"name": "backend"}],
        "statusCheckRollup": [],
        "reviewDecision": "REVIEW_REQUIRED",
        "isCrossRepository": False,
        "headRepositoryOwner": {"login": "test-owner"},
    }


def test_get_pull_request_success(pr_service, mock_gh_network, sample_pr_json):
    """Test successful PR retrieval"""
    # Setup mock
    mock_gh_network.run_command.return_value = json.dumps(sample_pr_json)

    # Call service
    result = pr_service.get_pull_request(123)

    # Assertions
    assert isinstance(result, ClientSuccess)
    assert result.data.number == 123
    assert result.data.title == "feat: Add new feature"
    assert result.data.state == "OPEN"
    assert result.data.author_name == "test-user"
    assert result.data.head_ref == "feat/new-feature"
    assert result.data.base_ref == "main"
    assert result.data.stats == "+50 -10"
    assert result.data.is_mergeable is True
    assert result.data.is_draft is False
    assert result.data.is_cross_repository is False
    assert result.data.head_repository_owner == "test-owner"
    assert result.data.checks_summary == "No checks"
    assert result.data.review_status_summary == "review required"
    assert "feature" in result.data.labels
    assert "backend" in result.data.labels

    # Verify network was called correctly
    call_args = mock_gh_network.run_command.call_args[0][0]
    assert "pr" in call_args
    assert "view" in call_args
    assert "123" in call_args


def test_get_pull_request_draft(pr_service, mock_gh_network, sample_pr_json):
    """Test retrieving draft PR"""
    # Make it a draft
    sample_pr_json["isDraft"] = True
    mock_gh_network.run_command.return_value = json.dumps(sample_pr_json)

    result = pr_service.get_pull_request(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.is_draft is True
    assert result.data.status_icon == "📝"  # Draft icon


def test_get_pull_request_merged(pr_service, mock_gh_network, sample_pr_json):
    """Test retrieving merged PR"""
    # Make it merged
    sample_pr_json["state"] = "MERGED"
    sample_pr_json["mergedAt"] = "2025-01-15T12:00:00Z"
    mock_gh_network.run_command.return_value = json.dumps(sample_pr_json)

    result = pr_service.get_pull_request(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.state == "MERGED"
    assert result.data.status_icon == "🟣"  # Merged icon


def test_get_pull_request_cross_repository(pr_service, mock_gh_network, sample_pr_json):
    """Test retrieving cross-repository PR metadata."""
    sample_pr_json["isCrossRepository"] = True
    sample_pr_json["headRepositoryOwner"] = {"login": "external-contributor"}
    mock_gh_network.run_command.return_value = json.dumps(sample_pr_json)

    result = pr_service.get_pull_request(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.is_cross_repository is True
    assert result.data.head_repository_owner == "external-contributor"


def test_get_pull_request_not_found(pr_service, mock_gh_network):
    """Test PR retrieval when PR doesn't exist"""
    # Setup mock to raise API error
    mock_gh_network.run_command.side_effect = GitHubAPIError("pull request not found")

    # Call service
    result = pr_service.get_pull_request(999)

    # Assertions
    assert isinstance(result, ClientError)
    assert "not found" in result.error_message.lower()


def test_get_pull_request_invalid_json(pr_service, mock_gh_network):
    """Test PR retrieval with invalid JSON response"""
    # Setup mock to return invalid JSON
    mock_gh_network.run_command.return_value = "invalid json {"

    # Call service
    result = pr_service.get_pull_request(123)

    # Assertions
    assert isinstance(result, ClientError)
    assert result.error_code == "JSON_PARSE_ERROR"


def test_merge_pr_success(pr_service, mock_gh_network):
    """Test successful PR merge"""
    # Setup mock - merge command returns output with SHA
    mock_gh_network.run_command.return_value = "✓ Merged pull request #123 (abc123d)"

    result = pr_service.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is True
    assert result.data.status_icon == "✅"
    assert result.data.sha_short == "abc123d"

    # Verify args
    call_args = mock_gh_network.run_command.call_args[0][0]
    assert "pr" in call_args
    assert "merge" in call_args
    assert "123" in call_args
    assert "--squash" in call_args


def test_merge_pr_invalid_method(pr_service, mock_gh_network):
    """Test merge with invalid merge method"""
    result = pr_service.merge_pr(123, merge_method="invalid-method")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is False
    assert result.data.status_icon == "❌"
    assert "invalid" in result.data.message.lower()


def test_merge_pr_failure(pr_service, mock_gh_network):
    """Test PR merge failure"""
    # Setup mock to raise API error
    mock_gh_network.run_command.side_effect = GitHubAPIError("PR not mergeable")

    result = pr_service.merge_pr(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is False
    assert result.data.status_icon == "❌"
    assert "not mergeable" in result.data.message.lower()


def test_merge_pr_without_graphql_merges_normally(pr_service, mock_gh_network):
    """Without a GraphQL network the merge queue cannot be detected: merge as always"""
    mock_gh_network.run_command.return_value = "✓ Merged pull request #123 (abc123d)"

    result = pr_service.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is True
    assert result.data.queued is False
    assert "--squash" in mock_gh_network.run_command.call_args[0][0]


def test_merge_pr_enqueues_when_merge_queue_enabled(queue_pr_service, mock_gh_network, mock_graphql_network):
    """With a merge queue the PR is queued, not merged, and no strategy is passed"""
    mock_graphql_network.run_query.side_effect = [
        merge_queue_response(enabled=True),
        merge_queue_response(enabled=True, in_queue=True, position=3, entry_state="QUEUED"),
    ]
    mock_gh_network.run_command.return_value = (
        "✓ Pull request #123 will be added to the merge queue"
    )

    result = queue_pr_service.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is False
    assert result.data.queued is True
    assert result.data.queue_position == 3
    assert result.data.status_icon == "⏳"

    call_args = mock_gh_network.run_command.call_args[0][0]
    assert "merge" in call_args
    assert "123" in call_args
    assert "--squash" not in call_args


def test_merge_pr_reuses_known_merge_queue_state(queue_pr_service, mock_gh_network, mock_graphql_network):
    """A known merge_queue_enabled skips the detection lookup"""
    mock_graphql_network.run_query.return_value = merge_queue_response(
        enabled=True, in_queue=True, position=1, entry_state="QUEUED"
    )
    mock_gh_network.run_command.return_value = "✓ queued"

    result = queue_pr_service.merge_pr(123, merge_method="squash", merge_queue_enabled=True)

    assert isinstance(result, ClientSuccess)
    assert result.data.queued is True
    # Only the read-back of the queue position, not a detection call before it
    assert mock_graphql_network.run_query.call_count == 1


def test_merge_pr_merges_when_no_merge_queue(queue_pr_service, mock_gh_network, mock_graphql_network):
    """No merge queue on the base branch: the requested strategy is used"""
    mock_graphql_network.run_query.return_value = merge_queue_response(enabled=False)
    mock_gh_network.run_command.return_value = "✓ Merged pull request #123 (abc123d)"

    result = queue_pr_service.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is True
    assert result.data.queued is False
    assert "--squash" in mock_gh_network.run_command.call_args[0][0]


def test_merge_pr_falls_back_to_regular_merge_when_detection_fails(
    queue_pr_service, mock_gh_network, mock_graphql_network
):
    """A failed detection must not block a merge"""
    mock_graphql_network.run_query.side_effect = GitHubAPIError("graphql down")
    mock_gh_network.run_command.return_value = "✓ Merged pull request #123 (abc123d)"

    result = queue_pr_service.merge_pr(123, merge_method="squash")

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is True
    assert "--squash" in mock_gh_network.run_command.call_args[0][0]


def test_merge_pr_reports_failed_enqueue(queue_pr_service, mock_gh_network, mock_graphql_network):
    """A failing enqueue is neither merged nor queued"""
    mock_graphql_network.run_query.return_value = merge_queue_response(enabled=True)
    mock_gh_network.run_command.side_effect = GitHubAPIError("not mergeable")

    result = queue_pr_service.merge_pr(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.merged is False
    assert result.data.queued is False
    assert "not mergeable" in result.data.message.lower()


def test_get_merge_queue_state_success(queue_pr_service, mock_graphql_network):
    """Merge queue state is read through GraphQL and pre-formatted"""
    mock_graphql_network.run_query.return_value = merge_queue_response(
        enabled=True, in_queue=True, position=2, entry_state="AWAITING_CHECKS"
    )

    result = queue_pr_service.get_merge_queue_state(123)

    assert isinstance(result, ClientSuccess)
    assert result.data.pr_number == 123
    assert result.data.is_merge_queue_enabled is True
    assert result.data.is_in_merge_queue is True
    assert result.data.queue_position == 2
    assert result.data.queue_entry_state == "AWAITING_CHECKS"
    assert "position 2" in result.data.summary


def test_get_merge_queue_state_pr_not_found(queue_pr_service, mock_graphql_network):
    """A missing PR node is reported as PR_NOT_FOUND"""
    mock_graphql_network.run_query.return_value = {"data": {"repository": {"pullRequest": None}}}

    result = queue_pr_service.get_merge_queue_state(123)

    assert isinstance(result, ClientError)
    assert result.error_code == "PR_NOT_FOUND"


def test_get_merge_queue_state_requires_graphql(pr_service):
    """Without a GraphQL network the lookup fails explicitly"""
    result = pr_service.get_merge_queue_state(123)

    assert isinstance(result, ClientError)
    assert result.error_code == "GRAPHQL_UNAVAILABLE"


def test_get_commit_review_context_success(pr_service, mock_gh_network):
    """Test commit context retrieval for a referenced SHA."""
    mock_gh_network.run_command.return_value = json.dumps(
        {
            "sha": "343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            "commit": {"message": "remove default state value"},
            "files": [
                {
                    "filename": "freyja-core/src/main/kotlin/.../BaseDialog.kt",
                    "status": "modified",
                    "patch": "@@ -36,7 +35,7 @@\n-fun BaseDialog(dialogState: DialogState = remember { DialogState() })\n+fun BaseDialog(dialogState: DialogState)\n",
                }
            ],
        }
    )

    result = pr_service.get_commit_review_context("343e2e9")

    assert isinstance(result, ClientSuccess)
    assert result.data.abbreviated_sha == "343e2e9"
    assert result.data.changed_files == ["freyja-core/src/main/kotlin/.../BaseDialog.kt"]
    assert "remove default state value" == result.data.message
    assert "diff --git a/freyja-core/src/main/kotlin/.../BaseDialog.kt" in result.data.patch_excerpt
    assert "repos/test-owner/test-repo/commits/343e2e9" in mock_gh_network.run_command.call_args[0][0][1]


def test_get_commit_review_context_uses_head_repo_when_provided(pr_service, mock_gh_network):
    """Test that repo_owner/repo_name override the configured base repo (fork PRs)."""
    mock_gh_network.run_command.return_value = json.dumps(
        {
            "sha": "343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            "commit": {"message": "remove default state value"},
            "files": [],
        }
    )

    result = pr_service.get_commit_review_context(
        "343e2e9", repo_owner="fork-owner", repo_name="fork-repo"
    )

    assert isinstance(result, ClientSuccess)
    assert "repos/fork-owner/fork-repo/commits/343e2e9" in mock_gh_network.run_command.call_args[0][0][1]


def test_get_commit_review_context_returns_parse_error_on_invalid_json(pr_service, mock_gh_network):
    """Test invalid commit payload handling."""
    mock_gh_network.run_command.return_value = "not json"

    result = pr_service.get_commit_review_context("343e2e9")

    assert isinstance(result, ClientError)
    assert result.error_code == "PARSE_ERROR"


def test_get_commit_review_context_returns_api_error_on_network_failure(pr_service, mock_gh_network):
    """Test GitHub API failure handling."""
    mock_gh_network.run_command.side_effect = GitHubAPIError("Not Found")

    result = pr_service.get_commit_review_context("343e2e9")

    assert isinstance(result, ClientError)
    assert result.error_code == "API_ERROR"


def test_get_pr_commit_sha_reads_head_ref_oid(pr_service, mock_gh_network):
    """Test the head SHA comes from headRefOid, not from the commits list."""
    mock_gh_network.run_command.return_value = json.dumps({"headRefOid": "4a999bc6"})

    result = pr_service.get_pr_commit_sha(3355)

    assert isinstance(result, ClientSuccess)
    assert result.data == "4a999bc6"
    args = mock_gh_network.run_command.call_args[0][0]
    assert "headRefOid" in args
    # gh caps the commits list at 100 entries, so its last element is not the head
    # on long-lived PRs; anchoring comments to it gets them rejected as unresolvable.
    assert "commits" not in args


def test_get_pr_commit_sha_missing_head_returns_error(pr_service, mock_gh_network):
    """Test an empty headRefOid is reported rather than passed on as a valid SHA."""
    mock_gh_network.run_command.return_value = json.dumps({"headRefOid": ""})

    result = pr_service.get_pr_commit_sha(123)

    assert isinstance(result, ClientError)
    assert result.error_code == "NO_COMMITS"


def test_get_pr_commit_sha_returns_api_error_on_network_failure(pr_service, mock_gh_network):
    """Test GitHub API failure handling."""
    mock_gh_network.run_command.side_effect = GitHubAPIError("Not Found")

    result = pr_service.get_pr_commit_sha(123)

    assert isinstance(result, ClientError)
    assert result.error_code == "API_ERROR"
