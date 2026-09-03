from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_github.models.view import UIMergeQueueState, UIPRMergeResult
from titan_plugin_github.steps.pull_request_steps import (
    get_pull_request_step,
    check_merge_queue_step,
    merge_pull_request_step,
    verify_pull_request_state_step,
    verify_merge_outcome_step,
)
from titan_plugin_github.steps.create_pr_step import create_pr_step


class MockTextual:
    def __init__(self):
        self.begin_step = Mock()
        self.end_step = Mock()
        self.error_text = Mock()
        self.success_text = Mock()
        self.warning_text = Mock()
        self.dim_text = Mock()
        self.text = Mock()

    def loading(self, _message):
        class _Loader:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Loader()


def make_context(mock_github_client=None, **data):
    ctx = WorkflowContext(textual=MockTextual(), github=mock_github_client)
    ctx.data.update(data)
    return ctx


def test_get_pull_request_step_success(sample_ui_pr):
    github = Mock()
    github.get_pull_request.return_value = ClientSuccess(data=sample_ui_pr, message="ok")
    ctx = make_context(github, pr_number=123)

    result = get_pull_request_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"pr_info": sample_ui_pr}
    github.get_pull_request.assert_called_once_with(123)
    ctx.textual.end_step.assert_called_once_with("success")


def test_get_pull_request_step_errors_without_pr_number():
    ctx = make_context(Mock())

    result = get_pull_request_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "No PR number in context"
    ctx.textual.end_step.assert_called_once_with("error")


def test_get_pull_request_step_client_error():
    github = Mock()
    github.get_pull_request.return_value = ClientError(error_message="boom")
    ctx = make_context(github, pr_number=123)

    result = get_pull_request_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "Failed to fetch PR: boom"
    ctx.textual.end_step.assert_called_once_with("error")


def test_merge_pull_request_step_success():
    github = Mock()
    merge_result = UIPRMergeResult(
        merged=True,
        status_icon="✅",
        sha_short="abc123d",
        message="Successfully merged",
    )
    github.merge_pr.return_value = ClientSuccess(data=merge_result, message="ok")
    ctx = make_context(github, pr_number=123, merge_method="squash")

    result = merge_pull_request_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {
        "merge_result": merge_result,
        "merge_queued": False,
        "expected_pr_state": "MERGED",
    }
    github.merge_pr.assert_called_once_with(
        123,
        merge_method="squash",
        commit_title=None,
        commit_message=None,
        merge_queue_enabled=None,
    )
    ctx.textual.end_step.assert_called_once_with("success")


def test_merge_pull_request_step_treats_unsuccessful_merge_as_error():
    github = Mock()
    merge_result = UIPRMergeResult(
        merged=False,
        status_icon="❌",
        sha_short="",
        message="Merge failed",
    )
    github.merge_pr.return_value = ClientSuccess(data=merge_result, message="failed")
    ctx = make_context(github, pr_number=123)

    result = merge_pull_request_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "Failed to merge PR #123: Merge failed"
    ctx.textual.end_step.assert_called_once_with("error")


def make_queue_state(
    *,
    enabled=True,
    in_queue=True,
    pr_state="OPEN",
    position=None,
    entry_state=None,
    summary="In merge queue",
):
    return UIMergeQueueState(
        pr_number=123,
        pr_state=pr_state,
        is_merge_queue_enabled=enabled,
        is_in_merge_queue=in_queue,
        queue_position=position,
        queue_entry_state=entry_state,
        summary=summary,
    )


def test_check_merge_queue_step_reports_enabled_queue():
    github = Mock()
    queue_state = make_queue_state(in_queue=False, summary="Merge queue required")
    github.get_merge_queue_state.return_value = ClientSuccess(data=queue_state, message="ok")
    ctx = make_context(github, pr_number=123)

    result = check_merge_queue_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {
        "merge_queue_enabled": True,
        "merge_queue_state": queue_state,
    }
    github.get_merge_queue_state.assert_called_once_with(123)
    ctx.textual.end_step.assert_called_once_with("success")


def test_check_merge_queue_step_reports_no_queue():
    github = Mock()
    queue_state = make_queue_state(enabled=False, in_queue=False, summary="No merge queue")
    github.get_merge_queue_state.return_value = ClientSuccess(data=queue_state, message="ok")
    ctx = make_context(github, pr_number=123)

    result = check_merge_queue_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["merge_queue_enabled"] is False


def test_check_merge_queue_step_does_not_block_on_lookup_failure():
    github = Mock()
    github.get_merge_queue_state.return_value = ClientError(error_message="graphql down")
    ctx = make_context(github, pr_number=123)

    result = check_merge_queue_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"merge_queue_enabled": False}
    ctx.textual.end_step.assert_called_once_with("success")


def test_merge_pull_request_step_reports_queued_pr():
    github = Mock()
    merge_result = UIPRMergeResult(
        merged=False,
        status_icon="⏳",
        sha_short="",
        message="PR #123 added to the merge queue",
        queued=True,
        queue_position=2,
    )
    github.merge_pr.return_value = ClientSuccess(data=merge_result, message="queued")
    ctx = make_context(github, pr_number=123, merge_method="squash", merge_queue_enabled=True)

    result = merge_pull_request_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {
        "merge_result": merge_result,
        "merge_queued": True,
        "expected_pr_state": "OPEN",
    }
    github.merge_pr.assert_called_once_with(
        123,
        merge_method="squash",
        commit_title=None,
        commit_message=None,
        merge_queue_enabled=True,
    )
    ctx.textual.end_step.assert_called_once_with("success")


def test_verify_merge_outcome_step_verifies_regular_merge(sample_ui_pr):
    github = Mock()
    merged_pr = sample_ui_pr
    merged_pr.state = "MERGED"
    github.get_pull_request.return_value = ClientSuccess(data=merged_pr, message="ok")
    ctx = make_context(github, pr_number=123)

    result = verify_merge_outcome_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"verified_pr_info": merged_pr}
    github.get_merge_queue_state.assert_not_called()
    ctx.textual.end_step.assert_called_once_with("success")


def test_verify_merge_outcome_step_errors_when_regular_merge_did_not_happen(sample_ui_pr):
    github = Mock()
    sample_ui_pr.state = "OPEN"
    github.get_pull_request.return_value = ClientSuccess(data=sample_ui_pr, message="ok")
    ctx = make_context(github, pr_number=123)

    result = verify_merge_outcome_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "PR #123 state mismatch: expected MERGED, got OPEN"
    ctx.textual.end_step.assert_called_once_with("error")


def test_verify_merge_outcome_step_accepts_queued_pr():
    github = Mock()
    queue_state = make_queue_state(position=1, entry_state="QUEUED")
    github.get_merge_queue_state.return_value = ClientSuccess(data=queue_state, message="ok")
    ctx = make_context(github, pr_number=123, merge_queued=True)

    result = verify_merge_outcome_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"merge_queue_state": queue_state}
    github.get_pull_request.assert_not_called()
    ctx.textual.end_step.assert_called_once_with("success")


def test_verify_merge_outcome_step_accepts_pr_already_merged_by_the_queue():
    github = Mock()
    queue_state = make_queue_state(in_queue=False, pr_state="MERGED", summary="Merged")
    github.get_merge_queue_state.return_value = ClientSuccess(data=queue_state, message="ok")
    ctx = make_context(github, pr_number=123, merge_queued=True)

    result = verify_merge_outcome_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"merge_queue_state": queue_state}


def test_verify_merge_outcome_step_errors_when_pr_left_the_queue():
    github = Mock()
    queue_state = make_queue_state(in_queue=False, pr_state="OPEN", summary="Not queued")
    github.get_merge_queue_state.return_value = ClientSuccess(data=queue_state, message="ok")
    ctx = make_context(github, pr_number=123, merge_queued=True)

    result = verify_merge_outcome_step(ctx)

    assert isinstance(result, Error)
    assert "left the merge queue" in result.message
    ctx.textual.end_step.assert_called_once_with("error")


def test_verify_pull_request_state_step_success(sample_ui_pr):
    github = Mock()
    merged_pr = sample_ui_pr
    merged_pr.state = "MERGED"
    github.get_pull_request.return_value = ClientSuccess(data=merged_pr, message="ok")
    ctx = make_context(github, pr_number=123, expected_state="merged")

    result = verify_pull_request_state_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"verified_pr_info": merged_pr}
    ctx.textual.end_step.assert_called_once_with("success")


def test_verify_pull_request_state_step_errors_on_mismatch(sample_ui_pr):
    github = Mock()
    github.get_pull_request.return_value = ClientSuccess(data=sample_ui_pr, message="ok")
    ctx = make_context(github, pr_number=123, expected_state="MERGED")

    result = verify_pull_request_state_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "PR #123 state mismatch: expected MERGED, got OPEN"
    ctx.textual.end_step.assert_called_once_with("error")


def test_verify_pull_request_state_step_requires_expected_state():
    ctx = make_context(Mock(), pr_number=123)

    result = verify_pull_request_state_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "No expected PR state in context"
    ctx.textual.end_step.assert_called_once_with("error")


def test_create_pr_step_uses_context_base_branch():
    github = Mock()
    github.config.auto_assign_prs = False
    github.create_pull_request.return_value = ClientSuccess(
        data=Mock(number=4105, url="https://github.example/pr/4105"),
        message="ok",
    )
    ctx = make_context(
        github,
        pr_title="notes: Add release notes for 26.18",
        pr_body="Release notes",
        pr_head_branch="notes/release-notes",
        pr_base_branch="rc/26.18",
    )
    ctx.git = Mock(main_branch="develop")

    result = create_pr_step(ctx)

    assert isinstance(result, Success)
    github.create_pull_request.assert_called_once()
    assert github.create_pull_request.call_args.kwargs["base"] == "rc/26.18"


def test_create_pr_step_falls_back_to_main_branch():
    github = Mock()
    github.config.auto_assign_prs = False
    github.create_pull_request.return_value = ClientSuccess(
        data=Mock(number=4106, url="https://github.example/pr/4106"),
        message="ok",
    )
    ctx = make_context(
        github,
        pr_title="notes: Add release notes for 26.18",
        pr_body="Release notes",
        pr_head_branch="notes/release-notes",
    )
    ctx.git = Mock(main_branch="develop")

    result = create_pr_step(ctx)

    assert isinstance(result, Success)
    github.create_pull_request.assert_called_once()
    assert github.create_pull_request.call_args.kwargs["base"] == "develop"


def test_create_pr_step_errors_without_base_branch():
    github = Mock()
    github.config.auto_assign_prs = False
    ctx = make_context(
        github,
        pr_title="notes: Add release notes for 26.18",
        pr_body="Release notes",
        pr_head_branch="notes/release-notes",
    )
    ctx.git = Mock(main_branch=None)

    result = create_pr_step(ctx)

    assert isinstance(result, Error)
    assert "pr_base_branch" in result.message
    github.create_pull_request.assert_not_called()
    ctx.textual.end_step.assert_called_once_with("error")
