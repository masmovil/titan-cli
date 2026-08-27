from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Skip, Success, WorkflowContext
from titan_plugin_github.models.view import UIRelease
from titan_plugin_github.steps.release_steps import select_release_step


class MockTextual:
    def __init__(self):
        self.begin_step = Mock()
        self.end_step = Mock()
        self.error_text = Mock()
        self.success_text = Mock()
        self.dim_text = Mock()
        self.ask_option = Mock()

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


def _release(tag_name="0.6.0", body="Release notes"):
    return UIRelease(
        tag_name=tag_name,
        title=tag_name,
        url=f"https://github.com/masorange/titan-cli/releases/tag/{tag_name}",
        is_prerelease=False,
        body=body,
    )


def test_select_release_step_errors_without_github_client():
    ctx = make_context(None)

    result = select_release_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "GitHub client not available"


def test_select_release_step_skips_when_no_releases():
    github = Mock()
    github.list_releases.return_value = ClientSuccess(data=[])
    ctx = make_context(github)

    result = select_release_step(ctx)

    assert isinstance(result, Skip)
    ctx.textual.end_step.assert_called_once_with("skip")


def test_select_release_step_errors_when_list_fails():
    github = Mock()
    github.list_releases.return_value = ClientError(error_message="boom", error_code="API_ERROR")
    ctx = make_context(github)

    result = select_release_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "boom"


def test_select_release_step_returns_selected_release_notes():
    github = Mock()
    listed = _release("0.6.0", body="")
    fetched = _release("0.6.0", body="- Added Slack plugin\n- Fixed thread resolution")
    github.list_releases.return_value = ClientSuccess(data=[listed])
    github.get_release.return_value = ClientSuccess(data=fetched)
    ctx = make_context(github)
    ctx.textual.ask_option.return_value = "0.6.0"

    result = select_release_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["selected_release_tag"] == "0.6.0"
    assert result.metadata["selected_release_notes"] == "- Added Slack plugin\n- Fixed thread resolution"
    github.get_release.assert_called_once_with("0.6.0")


def test_select_release_step_errors_when_no_selection():
    github = Mock()
    github.list_releases.return_value = ClientSuccess(data=[_release()])
    ctx = make_context(github)
    ctx.textual.ask_option.return_value = None

    result = select_release_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "No release was selected."
