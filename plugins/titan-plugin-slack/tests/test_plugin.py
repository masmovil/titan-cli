from pathlib import Path
from unittest.mock import MagicMock

import tomli

import pytest

from titan_plugin_slack.plugin import SlackPlugin
from titan_plugin_slack.exceptions import SlackConfigurationError
from titan_plugin_slack.oauth import SlackOAuthResult


class FakeBroker:
    """Dict-backed stand-in honoring the SecretBroker surface plugins use."""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.stored = {}

    def exists(self, key):
        return self.values.get(key) is not None

    def store(self, key, value):
        self.values[key] = value
        self.stored[key] = value

    def delete(self, key):
        self.values.pop(key, None)

    def create_client(self, key, builder, required=True):
        value = self.values.get(key)
        if value is None and required:
            raise KeyError(key)
        return builder(value)


def test_slack_plugin_basic_properties() -> None:
    plugin = SlackPlugin()

    assert plugin.name == "slack"
    assert plugin.description == "Provides Slack messaging and workspace integration."
    assert plugin.dependencies == []


def test_slack_plugin_exposes_public_steps() -> None:
    plugin = SlackPlugin()

    steps = plugin.get_steps()

    assert set(steps) == {
        "validate_connection",
        "list_public_channels",
        "list_users",
        "select_user_target",
        "select_channel_target",
        "select_default_or_search_channel_target",
        "select_target",
        "prepare_message_destination",
        "ensure_target_conversation",
        "read_recent_messages",
        "ai_summarize_messages",
        "open_direct_message",
        "format_markdown_message",
        "prompt_message_body",
        "post_message",
    }


def test_slack_plugin_exposes_workflows_path() -> None:
    plugin = SlackPlugin()

    assert plugin.workflows_path.name == "workflows"


def test_slack_plugin_exposes_config_schema() -> None:
    plugin = SlackPlugin()

    schema = plugin.get_config_schema()

    assert "user_token" in schema["properties"]
    assert schema["properties"]["default_team_id"]["config_scope"] == "project"
    assert schema["properties"]["default_channels"]["config_scope"] == "project"


def test_slack_plugin_initialize_requires_user_token() -> None:
    plugin = SlackPlugin()
    config = MagicMock()
    config.config.plugins = {"slack": MagicMock(config={"oauth_client_id": "123"})}
    config.get_project_name.return_value = "demo-project"
    broker = FakeBroker()

    with pytest.raises(SlackConfigurationError):
        plugin.initialize(config, broker)


def test_slack_plugin_initialize_uses_personal_token() -> None:
    plugin = SlackPlugin()
    config = MagicMock()
    config.config.plugins = {
        "slack": MagicMock(config={"default_team_id": "T123"})
    }
    config.get_project_name.return_value = "demo-project"
    broker = FakeBroker({"demo-project_slack_user_token": "xoxp-user-token"})

    plugin.initialize(config, broker)

    client = plugin.get_client()
    assert client.user_token == "xoxp-user-token"
    assert client.team_id == "T123"
    assert client.timeout == 30
    # No refresh token stored -> no refresher was built and nothing written.
    assert broker.stored == {}


def test_slack_plugin_initialize_refreshes_expiring_pkce_token(tmp_path: Path, monkeypatch) -> None:
    plugin = SlackPlugin()
    project_config_path = tmp_path / "project-config.toml"
    project_config_path.write_text(
        """
[plugins.slack]
enabled = true

[plugins.slack.config]
oauth_client_id = "123"
default_team_id = "T123"
default_team_name = "Acme"
granted_scopes = ["users:read"]
default_channels = ["general"]
""".strip()
    )

    config = MagicMock()
    config.project_config_path = project_config_path
    config.get_project_name.return_value = "demo-project"
    config.config = MagicMock()
    config.config.config_version = "1.0"
    config.config.plugins = {
        "slack": MagicMock(
            config={
                "oauth_client_id": "123",
                "default_team_id": "T123",
                "default_team_name": "Acme",
                "granted_scopes": ["users:read"],
                "default_channels": ["general"],
            }
        )
    }

    def fake_load() -> None:
        with open(project_config_path, "rb") as f:
            data = tomli.load(f)
        config.config.plugins = {
            "slack": MagicMock(config=data["plugins"]["slack"]["config"])
        }

    config.load = MagicMock(side_effect=fake_load)

    secret_values = {
        "demo-project_slack_user_token": "xoxe-old-token",
        "demo-project_slack_refresh_token": "xoxe-old-refresh-token",
        "demo-project_slack_token_expires_at": "1",
    }
    broker = FakeBroker(secret_values)

    refreshed = SlackOAuthResult(
        access_token="xoxe-new-token",
        refresh_token="xoxe-new-refresh-token",
        expires_in=43200,
        token_type="Bearer",
        granted_scopes=["users:read", "channels:read"],
        team_id="T123",
        team_name="Acme",
        authed_user_id=None,
    )

    class FakeFlow:
        def __init__(self, client_id):
            self.client_id = client_id

        def refresh_access_token(self, refresh_token):
            assert refresh_token == "xoxe-old-refresh-token"
            return refreshed

    monkeypatch.setattr("titan_plugin_slack.plugin.SlackOAuthFlow", FakeFlow)

    plugin.initialize(config, broker)

    client = plugin.get_client()
    assert client.user_token == "xoxe-new-token"
    assert broker.stored["demo-project_slack_user_token"] == "xoxe-new-token"
    assert broker.stored["demo-project_slack_refresh_token"] == "xoxe-new-refresh-token"
    assert "demo-project_slack_token_expires_at" in broker.stored
