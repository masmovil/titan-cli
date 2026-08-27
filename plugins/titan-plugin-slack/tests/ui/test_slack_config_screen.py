from pathlib import Path
import asyncio
from unittest.mock import MagicMock, PropertyMock

import tomli

from titan_plugin_slack.plugin import SlackPlugin
from titan_plugin_slack.oauth import SlackOAuthResult
from titan_plugin_slack.screens.slack_config_screen import SlackConfigScreen


class FakeBroker:
    """Dict-backed stand-in honoring the SecretBroker surface the screen uses."""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.stored = {}
        self.deleted = []
        self.store_error = None

    def exists(self, key):
        return self.values.get(key) is not None

    def store(self, key, value):
        if self.store_error is not None:
            raise self.store_error
        self.values[key] = value
        self.stored[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)

    def create_client(self, key, builder, required=True):
        value = self.values.get(key)
        if value is None and required:
            raise KeyError(key)
        return builder(value)


def _build_config(tmp_path: Path, token: str | None = None, plugin_config: dict | None = None):
    config = MagicMock()
    config._global_config_path = tmp_path / "config.toml"
    config.project_config_path = tmp_path / "project-config.toml"
    config.get_project_name.return_value = "demo-project"
    config.config = MagicMock()
    config.config.config_version = "1.0"
    config.config.plugins = {}
    if plugin_config is not None:
        config.config.plugins["slack"] = MagicMock(config=plugin_config)

    broker = FakeBroker(
        {"demo-project_slack_user_token": token} if token else {}
    )
    config.broker = broker
    config.broker_factory = MagicMock()
    config.broker_factory.for_plugin.return_value = broker
    config.load = MagicMock()
    return config


def test_slack_plugin_returns_custom_config_screen(tmp_path: Path) -> None:
    plugin = SlackPlugin()
    config = _build_config(tmp_path)

    assert plugin.has_custom_config_screen() is True
    assert isinstance(plugin.create_config_screen(config), SlackConfigScreen)


def test_slack_config_screen_reports_connection_state(tmp_path: Path) -> None:
    config = _build_config(
        tmp_path,
        token="xoxp-token",
        plugin_config={
            "oauth_client_id": "123",
            "default_team_id": "T123",
            "default_team_name": "Acme",
            "granted_scopes": ["users:read", "channels:read"],
            "default_channels": ["general", "release-notes"],
        },
    )
    screen = SlackConfigScreen(config)

    state = screen._get_connection_state()

    assert state.has_project_config is True
    assert state.has_token is True
    assert state.oauth_client_id == "123"
    assert state.default_team_id == "T123"
    assert state.default_team_name == "Acme"
    assert state.granted_scopes == ["users:read", "channels:read"]
    assert state.default_channels == ["general", "release-notes"]


def test_slack_config_screen_disconnect_only_deletes_project_token(tmp_path: Path) -> None:
    config = _build_config(tmp_path, token="xoxp-token")
    screen = SlackConfigScreen(config)

    app = MagicMock()
    type(screen).app = PropertyMock(return_value=app)

    screen._save_project_slack_config(
        {
            "oauth_client_id": "123",
            "default_team_id": "T123",
            "default_team_name": "Acme",
            "granted_scopes": ["users:read"],
            "default_channels": ["general"],
        }
    )
    screen._disconnect()

    assert "demo-project_slack_user_token" in config.broker.deleted
    assert "demo-project_slack_refresh_token" in config.broker.deleted
    assert "demo-project_slack_token_expires_at" in config.broker.deleted
    with open(config.project_config_path, "rb") as f:
        data = tomli.load(f)

    assert data["plugins"]["slack"]["enabled"] is True
    assert data["plugins"]["slack"]["config"]["oauth_client_id"] == "123"


def test_slack_config_screen_remove_project_config_clears_plugin_entry_and_token(tmp_path: Path) -> None:
    config = _build_config(tmp_path, token="xoxp-token")
    screen = SlackConfigScreen(config)

    app = MagicMock()
    type(screen).app = PropertyMock(return_value=app)

    screen._save_project_slack_config(
        {
            "oauth_client_id": "123",
            "default_team_id": "T123",
            "default_team_name": "Acme",
            "granted_scopes": ["users:read"],
            "default_channels": ["general"],
        }
    )

    screen._remove_project_config()

    assert "demo-project_slack_user_token" in config.broker.deleted
    assert "demo-project_slack_refresh_token" in config.broker.deleted
    assert "demo-project_slack_token_expires_at" in config.broker.deleted
    with open(config.project_config_path, "rb") as f:
        data = tomli.load(f)

    assert data.get("plugins", {}) == {}


def test_slack_config_screen_start_oauth_flow_runs_worker(tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    screen = SlackConfigScreen(config)

    app = MagicMock()
    type(screen).app = PropertyMock(return_value=app)

    screen.run_worker = MagicMock()
    screen._read_oauth_form_values = MagicMock(return_value=("123", ["general"]))
    screen._save_oauth_app_config = MagicMock()

    screen._start_oauth_flow()

    app.notify.assert_called_once_with(
        "Opening browser for Slack authorization...",
        severity="information",
    )
    screen.run_worker.assert_called_once()
    worker_coro = screen.run_worker.call_args.args[0]
    worker_coro.close()


def test_slack_config_screen_perform_oauth_connect_uses_backend(monkeypatch, tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    screen = SlackConfigScreen(config)

    expected = SlackOAuthResult(
        access_token="xoxp-token",
        refresh_token="xoxe-refresh-token",
        expires_in=43200,
        token_type="Bearer",
        granted_scopes=["users:read"],
        team_id="T123",
        team_name="Acme",
        authed_user_id="U123",
    )

    class FakeFlow:
        def __init__(self, client_id, redirect_port):
            self.client_id = client_id
            self.redirect_port = redirect_port

        def run(self):
            return expected

    monkeypatch.setattr(
        "titan_plugin_slack.screens.slack_config_screen.SlackOAuthFlow",
        FakeFlow,
    )

    result = screen._perform_oauth_connect("123")

    assert result == expected


def test_slack_config_screen_saves_oauth_app_config(tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    screen = SlackConfigScreen(config)

    screen._save_oauth_app_config("123", ["general", "release-notes"])

    with open(config.project_config_path, "rb") as f:
        data = tomli.load(f)

    slack_cfg = data["plugins"]["slack"]["config"]
    assert slack_cfg["oauth_client_id"] == "123"
    assert slack_cfg["default_channels"] == ["general", "release-notes"]
    assert data["plugins"]["slack"]["enabled"] is True


def test_slack_config_screen_oauth_connect_fails_when_keyring_write_fails(tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    screen = SlackConfigScreen(config)

    app = MagicMock()
    type(screen).app = PropertyMock(return_value=app)

    expected = SlackOAuthResult(
        access_token="xoxp-token",
        refresh_token="xoxe-refresh-token",
        expires_in=43200,
        token_type="Bearer",
        granted_scopes=["users:read"],
        team_id="T123",
        team_name="Acme",
        authed_user_id="U123",
    )
    screen._perform_oauth_connect = MagicMock(return_value=expected)
    config.broker.store_error = RuntimeError("keyring unavailable")
    screen._remove_project_config = MagicMock()

    asyncio.run(screen._run_oauth_connect("123", ["general"]))

    app.notify.assert_called_once_with(
        "Slack OAuth failed: keyring unavailable",
        severity="error",
    )
    screen._remove_project_config.assert_called_once()


def test_slack_config_screen_save_project_config_enables_plugin(tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    screen = SlackConfigScreen(config)

    screen._save_project_slack_config({"oauth_client_id": "123"})

    with open(config.project_config_path, "rb") as f:
        data = tomli.load(f)

    assert data["plugins"]["slack"]["enabled"] is True


def test_parse_default_channels_normalizes_and_deduplicates() -> None:
    result = SlackConfigScreen._parse_default_channels(
        "#general, release-notes, general,  ,\n#alerts"
    )

    assert result == ["general", "release-notes", "alerts"]
