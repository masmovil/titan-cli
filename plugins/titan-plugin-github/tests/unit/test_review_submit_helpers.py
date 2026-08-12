from types import SimpleNamespace
from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess

from titan_plugin_github.operations.review_action_operations import classify_github_review_rejection
from titan_plugin_github.steps.code_review_steps import _filter_invalid_inline_comments


def test_filter_invalid_inline_comments_keeps_only_github_valid_ones():
    github = Mock()
    github.create_draft_review.side_effect = [
        ClientSuccess(data=101, message="ok"),
        ClientError(error_message="HTTP 422 invalid comment", error_code="API_ERROR"),
    ]
    github.delete_review.return_value = ClientSuccess(data=None, message="deleted")
    ctx = SimpleNamespace(github=github)

    payload = {
        "commit_id": "abc123",
        "comments": [
            {"path": "src/a.py", "line": 10, "side": "RIGHT", "body": "valid"},
            {"path": "src/b.py", "line": 20, "side": "RIGHT", "body": "invalid"},
        ],
        "body": "general body",
    }

    filtered_payload, rejected = _filter_invalid_inline_comments(ctx, 42, payload)

    assert filtered_payload["comments"] == [payload["comments"][0]]
    # The rejected comment's content degrades to the review body — never dropped.
    assert filtered_payload["body"].startswith("general body")
    assert "**src/b.py** (line 20):\ninvalid" in filtered_payload["body"]
    assert len(rejected) == 1
    assert rejected[0]["path"] == "src/b.py"
    github.delete_review.assert_called_once_with(42, 101)


def test_filter_invalid_inline_comments_builds_body_when_none_existed():
    github = Mock()
    github.create_draft_review.side_effect = [
        ClientError(error_message="Path could not be resolved", error_code="API_ERROR"),
    ]
    ctx = SimpleNamespace(github=github)

    payload = {
        "commit_id": "abc123",
        "comments": [{"path": "src/b.py", "line": 20, "side": "RIGHT", "body": "finding text"}],
    }

    filtered_payload, rejected = _filter_invalid_inline_comments(ctx, 42, payload)

    assert filtered_payload["comments"] == []
    assert filtered_payload["body"] == "**src/b.py** (line 20):\nfinding text"
    assert len(rejected) == 1


def test_classify_github_review_rejection():
    assert classify_github_review_rejection("Line could not be resolved") == "line_not_resolved"
    assert classify_github_review_rejection("Path could not be resolved") == "path_not_resolved"
    assert classify_github_review_rejection("User can only have one pending review per pull request") == "pending_review_exists"
    assert classify_github_review_rejection("something else") == "unknown"
