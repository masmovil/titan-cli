from unittest.mock import MagicMock

from titan_cli.core.result import ClientSuccess
from titan_cli.engine import Error, Success
from titan_cli.engine.context import WorkflowContext
from titan_plugin_slack.models import UISlackAuth, UISlackChannel, UISlackUser
from titan_plugin_slack.steps.discovery_steps import (
    list_public_channels_step,
    list_users_step,
    validate_connection_step,
)


def _build_context() -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.textual = MagicMock()

    loading_mock = MagicMock()
    loading_mock.__enter__ = MagicMock(return_value=loading_mock)
    loading_mock.__exit__ = MagicMock(return_value=None)
    ctx.textual.loading = MagicMock(return_value=loading_mock)

    return ctx


def test_validate_connection_step_returns_error_without_slack_client() -> None:
    ctx = _build_context()

    result = validate_connection_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "Slack client not available"


def test_validate_connection_step_returns_auth_metadata() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.slack.auth_test.return_value = ClientSuccess(
        data=UISlackAuth(
            user_id="U123",
            team_id="T123",
            team="Acme",
            url="https://acme.slack.com",
            bot_id=None,
        )
    )

    result = validate_connection_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {
        "slack_auth": UISlackAuth(
            user_id="U123",
            team_id="T123",
            team="Acme",
            url="https://acme.slack.com",
            bot_id=None,
        ),
        "slack_team_id": "T123",
        "slack_team_name": "Acme",
        "slack_user_id": "U123",
        "slack_user_name": None,
    }


def test_list_public_channels_step_returns_channels_and_cursor() -> None:
    ctx = _build_context()
    ctx.data.update({"slack_limit": 25, "slack_cursor": "cursor-1"})
    ctx.slack = MagicMock()
    ctx.slack.list_public_channels.return_value = ClientSuccess(
        data=(
            [
                UISlackChannel(id="C123", name="general"),
                UISlackChannel(id="C456", name="announcements"),
            ],
            "cursor-2",
        )
    )

    result = list_public_channels_step(ctx)

    assert isinstance(result, Success)
    ctx.slack.list_public_channels.assert_called_once_with(
        limit=25,
        cursor="cursor-1",
        exclude_archived=True,
    )
    assert result.metadata == {
        "slack_channels": [
            UISlackChannel(id="C123", name="general"),
            UISlackChannel(id="C456", name="announcements"),
        ],
        "slack_channels_next_cursor": "cursor-2",
    }


def test_list_users_step_returns_users_and_cursor() -> None:
    ctx = _build_context()
    ctx.data.update({"slack_limit": 10, "slack_cursor": "cursor-a"})
    ctx.slack = MagicMock()
    ctx.slack.list_users.return_value = ClientSuccess(
        data=(
            [
                UISlackUser(id="U123", name="alex", real_name="Alex"),
                UISlackUser(id="U456", name="sam", real_name="Sam"),
            ],
            "cursor-b",
        )
    )

    result = list_users_step(ctx)

    assert isinstance(result, Success)
    ctx.slack.list_users.assert_called_once_with(limit=10, cursor="cursor-a")
    assert result.metadata == {
        "slack_users": [
            UISlackUser(id="U123", name="alex", real_name="Alex"),
            UISlackUser(id="U456", name="sam", real_name="Sam"),
        ],
        "slack_users_next_cursor": "cursor-b",
    }
