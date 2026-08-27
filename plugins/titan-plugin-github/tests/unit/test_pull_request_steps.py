from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_github.models.view import UIPRMergeResult
from titan_plugin_github.steps.pull_request_steps import (
    get_pull_request_step,
    merge_pull_request_step,
    verify_pull_request_state_step,
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
    assert result.metadata == {"merge_result": merge_result}
    github.merge_pr.assert_called_once_with(
        123,
        merge_method="squash",
        commit_title=None,
        commit_message=None,
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
