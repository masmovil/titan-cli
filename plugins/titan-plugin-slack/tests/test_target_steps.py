from unittest.mock import MagicMock

from titan_cli.core.result import ClientSuccess
from titan_cli.engine import Error, Success
from titan_cli.engine.context import WorkflowContext
from titan_plugin_slack.models import UISlackChannel, UISlackTarget, UISlackUser
from titan_plugin_slack.steps.target_steps import (
    select_channel_target_step,
    select_default_or_search_channel_target_step,
    select_user_target_step,
)


def _build_context() -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.textual = MagicMock()
    return ctx


def test_select_user_target_returns_error_without_source_users() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.textual.ask_text.return_value = "alex"
    ctx.slack.search_users.return_value = ClientSuccess(data=[])

    result = select_user_target_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "No Slack users matched that query."


def test_select_user_target_returns_target_metadata() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.data["slack_team_id"] = "T1"
    ctx.textual.ask_text.return_value = "alex"
    user = UISlackUser(id="U1", name="alex", real_name="Alex Smith")
    ctx.slack.search_users.return_value = ClientSuccess(data=[user])
    ctx.textual.ask_option.return_value = user

    result = select_user_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target"] == UISlackTarget(
        target_type="user",
        target_id="U1",
        target_name="Alex Smith",
        team_id="T1",
        connection_id=None,
    )
    assert result.metadata["slack_target_type"] == "user"
    assert result.metadata["slack_target_id"] == "U1"
    assert result.metadata["slack_target_name"] == "Alex Smith"


def test_select_channel_target_returns_error_for_short_query() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.textual.ask_text.return_value = "g"

    result = select_channel_target_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "Enter at least 2 characters to search Slack channels."


def test_select_channel_target_returns_target_metadata() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.textual.ask_text.return_value = "eng"
    channel = UISlackChannel(id="C2", name="eng-backend")
    ctx.slack.search_channels.return_value = ClientSuccess(data=[channel])
    ctx.textual.ask_option.return_value = channel

    result = select_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target"] == UISlackTarget(
        target_type="channel",
        target_id="C2",
        target_name="eng-backend",
        team_id=None,
        connection_id=None,
    )
    assert result.metadata["slack_target_type"] == "channel"
    assert result.metadata["slack_target_id"] == "C2"
    assert result.metadata["slack_target_name"] == "eng-backend"


def test_select_default_or_search_channel_target_uses_configured_default() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = ["eng-backend"]
    channel = UISlackChannel(id="C2", name="eng-backend")
    ctx.textual.ask_multiselect.return_value = ["eng-backend"]
    ctx.slack.search_channels.return_value = ClientSuccess(data=[channel])

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_conversation_ids"] == ["C2"]
    assert result.metadata["slack_unresolved_channels"] == []


def test_select_default_or_search_channel_target_falls_back_to_unified_search_when_no_defaults() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = []
    ctx.textual.ask_text.return_value = "eng"
    channel = UISlackChannel(id="C2", name="eng-backend")
    ctx.slack.search_users.return_value = ClientSuccess(data=[])
    ctx.slack.search_channels.return_value = ClientSuccess(data=[channel])
    target = UISlackTarget(target_type="channel", target_id="C2", target_name="eng-backend")
    ctx.textual.ask_option.return_value = target

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target_id"] == "C2"


def test_select_default_or_search_channel_target_falls_back_to_a_person_when_no_defaults() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = []
    ctx.textual.ask_text.return_value = "alex"
    user = UISlackUser(id="U1", name="alex", real_name="Alex Smith")
    ctx.slack.search_users.return_value = ClientSuccess(data=[user])
    ctx.slack.search_channels.return_value = ClientSuccess(data=[])
    target = UISlackTarget(target_type="user", target_id="U1", target_name="Alex Smith")
    ctx.textual.ask_option.return_value = target

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target_type"] == "user"
    assert result.metadata["slack_target_id"] == "U1"


def test_select_default_or_search_channel_target_no_channel_checked_falls_back_to_unified_search() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = ["eng-backend"]
    ctx.textual.ask_multiselect.return_value = []
    ctx.textual.ask_option.return_value = UISlackTarget(
        target_type="user", target_id="U1", target_name="Alex Smith"
    )
    ctx.textual.ask_text.return_value = "alex"
    user = UISlackUser(id="U1", name="alex", real_name="Alex Smith")
    ctx.slack.search_users.return_value = ClientSuccess(data=[user])
    ctx.slack.search_channels.return_value = ClientSuccess(data=[])

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target_type"] == "user"
    assert result.metadata["slack_target_id"] == "U1"


def test_select_default_or_search_channel_target_skips_unresolved_channel_but_posts_to_rest() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = ["eng-backend", "ghost-channel"]
    ctx.textual.ask_multiselect.return_value = ["eng-backend", "ghost-channel"]
    ctx.slack.search_channels.side_effect = [
        ClientSuccess(data=[UISlackChannel(id="C2", name="eng-backend")]),
        ClientSuccess(data=[]),
    ]

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_conversation_ids"] == ["C2"]
    assert result.metadata["slack_unresolved_channels"] == ["ghost-channel"]
    ctx.textual.warning_text.assert_called_once()


def test_select_default_or_search_channel_target_errors_when_no_channel_resolves() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = ["ghost-channel"]
    ctx.textual.ask_multiselect.return_value = ["ghost-channel"]
    ctx.slack.search_channels.return_value = ClientSuccess(data=[])

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Error)


def test_select_default_or_search_channel_target_auto_selects_preferred_channel() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.data["slack_preferred_target"] = "titan-releases"
    channel = UISlackChannel(id="C9", name="titan-releases")
    ctx.slack.search_users.return_value = ClientSuccess(data=[])
    ctx.slack.search_channels.return_value = ClientSuccess(data=[channel])

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target_type"] == "channel"
    assert result.metadata["slack_target_id"] == "C9"
    assert result.metadata["slack_target_name"] == "titan-releases"
    ctx.textual.ask_option.assert_not_called()


def test_select_default_or_search_channel_target_auto_selects_preferred_person() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.data["slack_preferred_target"] = "Alejandro Lopez Ruiz"
    user = UISlackUser(id="U9", name="alopez", real_name="Alejandro Lopez Ruiz")
    ctx.slack.search_users.return_value = ClientSuccess(data=[user])
    ctx.slack.search_channels.return_value = ClientSuccess(data=[])

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target_type"] == "user"
    assert result.metadata["slack_target_id"] == "U9"
    assert result.metadata["slack_target_name"] == "Alejandro Lopez Ruiz"
    ctx.textual.ask_option.assert_not_called()


def test_select_default_or_search_channel_target_falls_back_when_preferred_target_ambiguous() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.default_channels = ["eng-backend"]
    ctx.data["slack_preferred_target"] = "does-not-exist"
    ctx.slack.search_users.return_value = ClientSuccess(data=[])
    ctx.slack.search_channels.side_effect = [
        ClientSuccess(data=[]),  # resolving the preferred target fails
        ClientSuccess(data=[UISlackChannel(id="C2", name="eng-backend")]),  # configured default
    ]
    ctx.textual.ask_multiselect.return_value = ["eng-backend"]

    result = select_default_or_search_channel_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_conversation_ids"] == ["C2"]
    ctx.textual.dim_text.assert_called_once()
