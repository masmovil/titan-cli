from dataclasses import dataclass
import asyncio
import time

import tomli
import tomli_w
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Input, Static

from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import BoldPrimaryText, BoldText, Button, DimText, Text
from titan_cli.ui.tui.screens.base import BaseScreen
from titan_cli.core.logging import get_logger

from titan_cli.core.result import ClientError, ClientSuccess

from ..clients.slack_client import SlackClient
from ..config import (
    build_project_slack_refresh_token_key,
    build_project_slack_token_expires_at_key,
    build_project_slack_token_key,
)
from ..oauth import SlackOAuthFlow, SlackOAuthResult


logger = get_logger(__name__)
DEFAULT_OAUTH_REDIRECT_PORT = 8765


@dataclass
class SlackConnectionState:
    """Current Slack connection state for the active user."""

    has_project_config: bool
    has_token: bool
    oauth_client_id: str | None
    default_team_id: str | None
    default_team_name: str | None
    granted_scopes: list[str]
    default_channels: list[str]


class SlackConfigScreen(BaseScreen):
    """Slack-specific configuration screen."""

    CSS = """
    SlackConfigScreen {
        align: center middle;
    }

    #slack-config-container {
        width: 100%;
        height: 1fr;
        background: $surface-lighten-1;
        padding: 0 2 1 2;
    }

    #slack-config-panel {
        width: 100%;
        height: 1fr;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
        layout: vertical;
    }

    #slack-config-scroll {
        height: 1fr;
    }

    #slack-config-body {
        padding: 1;
        height: auto;
    }

    .slack-section-title {
        margin-top: 1;
    }

    .slack-section-body {
        height: auto;
        margin-bottom: 1;
    }

    #slack-config-buttons {
        height: auto;
        padding: 1 2;
        background: $surface-lighten-1;
        border-top: solid $primary;
        align: right middle;
    }

    #slack-config-buttons Button {
        margin-left: 1;
    }

    Input {
        width: 100%;
        margin-top: 1;
        margin-bottom: 1;
        border: solid $accent;
    }

    Input:focus {
        border: solid $primary;
    }
    """

    def __init__(self, config):
        super().__init__(
            config,
            title=f"{Icons.SETTINGS} Configure Slack",
            show_back=True,
            show_status_bar=False,
        )
        self._reconfigure_project_mode = False
        self._has_changes = False

    def compose_content(self) -> ComposeResult:
        with Container(id="slack-config-container"):
            panel = Container(id="slack-config-panel")
            panel.border_title = "Slack Connection"
            with panel:
                with VerticalScroll(id="slack-config-scroll"):
                    with Container(id="slack-config-body"):
                        yield BoldPrimaryText("Connect your personal Slack account", id="slack-title")
                        yield Text("")
                        yield Static(id="slack-intro")
                        yield Text("")

                        yield BoldText("Current Status", classes="slack-section-title")
                        yield Static(id="slack-status-block", classes="slack-section-body")

                        yield BoldText("OAuth App Configuration", classes="slack-section-title")
                        yield Static(id="slack-oauth-help", classes="slack-section-body")
                        yield DimText("Client ID")
                        yield Input(id="oauth-client-id-input")
                        yield DimText("Default Channels")
                        yield Input(placeholder="general, release-notes", id="default-channels-input")
                        yield DimText("Enter channel names separated by commas, for example: general, release-notes")
                        yield Text("")

                        yield BoldText("Required Capabilities", classes="slack-section-title")
                        yield Static(id="slack-scopes-block", classes="slack-section-body")
                        yield Static(id="slack-connect-help", classes="slack-section-body")

                with Horizontal(id="slack-config-buttons"):
                    yield Button("Configure Slack", variant="primary", id="connect-button")
                    yield Button("Validate Connection", variant="default", id="validate-button")
                    yield Button("Reconfigure Project", variant="warning", id="reconfigure-project-button")
                    yield Button("Disconnect Account", variant="default", id="disconnect-button")
                    yield Button("Remove Project Config", variant="error", id="remove-project-config-button")
                    yield Button("Close", variant="default", id="close-button")

    def on_mount(self) -> None:
        self._refresh_view()

    def _load_plugin_config(self) -> dict:
        plugin_cfg = getattr(self.config.config, "plugins", {}).get("slack") if self.config.config else None
        if not plugin_cfg:
            return {}
        return plugin_cfg.config if hasattr(plugin_cfg, "config") else {}

    def _has_user_token(self) -> bool:
        return bool(self.config.secrets.get(self._get_project_token_key()))

    def _get_project_name(self) -> str:
        project_name = self.config.get_project_name()
        if not project_name:
            raise ValueError("Slack configuration requires an active Titan project.")
        return project_name

    def _get_project_token_key(self) -> str:
        return build_project_slack_token_key(self._get_project_name())

    def _get_project_refresh_token_key(self) -> str:
        return build_project_slack_refresh_token_key(self._get_project_name())

    def _get_project_token_expires_at_key(self) -> str:
        return build_project_slack_token_expires_at_key(self._get_project_name())

    def _get_connection_state(self) -> SlackConnectionState:
        plugin_config = self._load_plugin_config()
        return SlackConnectionState(
            has_project_config=bool(plugin_config),
            has_token=self._has_user_token(),
            oauth_client_id=plugin_config.get("oauth_client_id"),
            default_team_id=plugin_config.get("default_team_id"),
            default_team_name=plugin_config.get("default_team_name"),
            granted_scopes=plugin_config.get("granted_scopes", []),
            default_channels=plugin_config.get("default_channels", []),
        )

    def _save_project_slack_config(self, updates: dict[str, object | None]) -> None:
        project_cfg_path = self.config.project_config_path
        if not project_cfg_path:
            raise ValueError("Slack configuration requires a project config path.")

        config_data = {}
        if project_cfg_path.exists():
            with open(project_cfg_path, "rb") as f:
                config_data = tomli.load(f)

        config_data.setdefault("config_version", getattr(self.config.config, "config_version", "1.0"))
        project_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        plugins = config_data.setdefault("plugins", {})
        plugin_table = plugins.setdefault("slack", {})
        plugin_table["enabled"] = True
        plugin_config = plugin_table.setdefault("config", {})

        for key, value in updates.items():
            if value is None:
                plugin_config.pop(key, None)
            else:
                plugin_config[key] = value

        with open(project_cfg_path, "wb") as f:
            tomli_w.dump(config_data, f)

        self.config.load()
        self._has_changes = True

    def _refresh_view(self) -> None:
        state = self._get_connection_state()
        try:
            intro = self.query_one("#slack-intro", Static)
            status_block = self.query_one("#slack-status-block", Static)
            oauth_help = self.query_one("#slack-oauth-help", Static)
            scopes_block = self.query_one("#slack-scopes-block", Static)
            connect_help = self.query_one("#slack-connect-help", Static)
            client_id_input = self.query_one("#oauth-client-id-input", Input)
            default_channels_input = self.query_one("#default-channels-input", Input)
            connect_button = self.query_one("#connect-button", Button)
            validate_button = self.query_one("#validate-button", Button)
            reconfigure_button = self.query_one("#reconfigure-project-button", Button)
            disconnect_button = self.query_one("#disconnect-button", Button)
            remove_project_button = self.query_one("#remove-project-config-button", Button)
        except NoMatches:
            return

        if state.has_project_config and state.has_token:
            repo_status = "Configured"
            account_status = "Connected"
        elif state.has_project_config:
            repo_status = "Configured"
            account_status = "Not connected"
        else:
            repo_status = "Not configured"
            account_status = "Not connected"
        scopes = ", ".join(state.granted_scopes) if state.granted_scopes else "Not recorded"

        if state.has_project_config and self._reconfigure_project_mode:
            intro.update(
                "You are editing this repository's shared Slack configuration.\n"
                "Saving and connecting will update the project Slack App settings, default channels, and then sign in with your account."
            )
        elif state.has_project_config:
            intro.update(
                "This repository has its own Slack configuration.\n"
                "Each user only needs to sign in with their own Slack account for this project."
            )
        else:
            intro.update(
                "Slack is not configured for this repository yet.\n"
                "Configure the repository's Slack App and default channels first, then sign in with your personal Slack account."
            )
        status_block.update(
            f"  Repository Config: {repo_status}\n"
            f"  Personal Account: {account_status}\n"
            f"  OAuth Client ID: {state.oauth_client_id or 'Not set'}\n"
            f"  OAuth Redirect Port: {DEFAULT_OAUTH_REDIRECT_PORT}\n"
            f"  Team ID: {state.default_team_id or 'Not set'}\n"
            f"  Team Name: {state.default_team_name or 'Not set'}\n"
            f"  Recorded Granted Scopes: {scopes}\n"
            f"  Default Channels: {', '.join('#' + channel for channel in state.default_channels) if state.default_channels else 'Not set'}"
        )
        oauth_help.update(
            "Titan will open Slack in your browser and complete the OAuth PKCE flow.\n"
            "Create your project's Slack App, enable PKCE, and configure this exact redirect URL in Slack OAuth settings:\n"
            f"  {self._build_redirect_uri()}\n"
            "The redirect URL in Slack must match exactly, including host, port, and path.\n"
            "For example, `127.0.0.1` and `localhost` are different values for Slack."
        )
        scopes_block.update(
            "Slack currently requests these scopes during OAuth:\n"
            "  - users:read\n"
            "  - channels:read, channels:history, channels:write\n"
            "  - groups:read, groups:history, groups:write\n"
            "  - im:history, im:write\n"
            "  - mpim:history, mpim:write\n"
            "  - chat:write\n\n"
            "Current Status shows the scopes recorded from the last successful OAuth connection. "
            "Use Reconnect Slack after changing scopes in your Slack App."
        )
        if state.has_project_config and self._reconfigure_project_mode:
            connect_help.update(
                "Use Save Config and Connect to replace this repository's Slack App configuration and then sign in with Slack."
            )
        elif state.has_project_config and not state.has_token:
            connect_help.update(
                "Use Sign In to Slack to connect your own account using this repository's existing Slack configuration."
            )
        elif state.has_project_config:
            connect_help.update(
                "Use Reconnect Slack if you need to refresh your personal Slack account for this repository."
            )
        else:
            connect_help.update(
                "Use Configure Slack to save this repository's Slack App configuration and sign in with Slack."
            )

        client_id_input.value = state.oauth_client_id or ""
        default_channels_input.value = ", ".join(state.default_channels)
        client_id_input.disabled = state.has_project_config and not self._reconfigure_project_mode
        default_channels_input.disabled = (
            state.has_project_config and not self._reconfigure_project_mode
        )

        if state.has_project_config and self._reconfigure_project_mode:
            connect_button.label = "Save Config and Connect"
        elif state.has_project_config and state.has_token:
            connect_button.label = "Reconnect Slack"
        elif state.has_project_config:
            connect_button.label = "Sign In to Slack"
        else:
            connect_button.label = "Configure Slack"

        validate_button.disabled = not state.has_token
        reconfigure_button.disabled = not state.has_project_config
        disconnect_button.disabled = not state.has_token
        remove_project_button.disabled = not state.has_project_config

    @staticmethod
    def _build_redirect_uri() -> str:
        """Build the localhost redirect URI shown to the user."""
        return f"http://127.0.0.1:{DEFAULT_OAUTH_REDIRECT_PORT}/slack/callback"

    @staticmethod
    def _parse_default_channels(raw_value: str) -> list[str]:
        """Parse a comma-separated list of default channel names."""
        channels: list[str] = []
        seen: set[str] = set()
        for item in raw_value.replace("\n", ",").split(","):
            channel = item.strip().lstrip("#")
            if not channel:
                continue
            key = channel.casefold()
            if key in seen:
                continue
            seen.add(key)
            channels.append(channel)
        return channels

    def _read_oauth_form_values(self) -> tuple[str, list[str]]:
        """Read and validate the OAuth app form values from the screen."""
        client_id = self.query_one("#oauth-client-id-input", Input).value.strip()
        default_channels_raw = self.query_one("#default-channels-input", Input).value.strip()

        if not client_id:
            raise ValueError("Slack OAuth client ID is required.")

        return client_id, self._parse_default_channels(default_channels_raw)

    def _save_oauth_app_config(self, client_id: str, default_channels: list[str]) -> None:
        """Persist OAuth app settings for Slack."""
        self._save_project_slack_config(
            {
                "oauth_client_id": client_id,
                "default_channels": default_channels,
            }
        )

    def _perform_oauth_connect(self, client_id: str) -> SlackOAuthResult:
        """Run the synchronous Slack OAuth backend flow."""
        flow = SlackOAuthFlow(
            client_id=client_id,
            redirect_port=DEFAULT_OAUTH_REDIRECT_PORT,
        )
        return flow.run()

    def _start_oauth_flow(self) -> None:
        """Start the Slack OAuth flow in a background worker."""
        try:
            plugin_config = self._load_plugin_config()
            if plugin_config and not self._reconfigure_project_mode:
                client_id = plugin_config.get("oauth_client_id")
                default_channels = plugin_config.get("default_channels", [])
                if not client_id:
                    raise ValueError(
                        "This repository is marked as configured for Slack but has no OAuth client ID. Reconfigure the project to continue."
                    )
            else:
                client_id, default_channels = self._read_oauth_form_values()
        except Exception as exc:
            logger.exception("slack_oauth_setup_failed")
            self.app.notify(f"Slack OAuth setup failed: {exc}", severity="error")
            return

        self.app.notify("Opening browser for Slack authorization...", severity="information")
        self.run_worker(
            self._run_oauth_connect(client_id, default_channels),
            exclusive=True,
        )

    async def _run_oauth_connect(self, client_id: str, default_channels: list[str]) -> None:
        """Run the Slack OAuth flow without blocking the UI thread."""
        config_written = False
        token_written = False
        try:
            result = await asyncio.to_thread(
                self._perform_oauth_connect,
                client_id,
            )
            self._save_project_slack_config(
                {
                    "oauth_client_id": client_id,
                    "default_team_id": result.team_id,
                    "default_team_name": result.team_name,
                    "token_type": None,
                    "token_expires_at": None,
                    "granted_scopes": result.granted_scopes,
                    "default_channels": default_channels,
                }
            )
            config_written = True
            self.config.secrets.set(
                self._get_project_token_key(), result.access_token, scope="user"
            )
            if result.refresh_token:
                self.config.secrets.set(
                    self._get_project_refresh_token_key(), result.refresh_token, scope="user"
                )
            if result.expires_in:
                self.config.secrets.set(
                    self._get_project_token_expires_at_key(),
                    str(int(time.time()) + result.expires_in),
                    scope="user",
                )
            token_written = True
            # The plugin reads this token while initializing, and the config
            # reload above ran before the token existed. Nothing in the config
            # files changed since, so only an explicit rebuild picks it up.
            self.config.load(force_plugin_init=True)
            self._reconfigure_project_mode = False
            self._has_changes = True
            self.app.notify("Slack connected successfully.", severity="information")
            self.dismiss(result=True)
        except Exception as exc:
            if token_written:
                try:
                    self.config.secrets.delete(self._get_project_token_key(), scope="user")
                    self.config.secrets.delete(
                        self._get_project_refresh_token_key(), scope="user"
                    )
                    self.config.secrets.delete(
                        self._get_project_token_expires_at_key(), scope="user"
                    )
                except Exception:
                    pass

            if config_written:
                try:
                    self._remove_project_config()
                except Exception:
                    pass

            logger.exception("slack_oauth_run_failed")
            self.app.notify(f"Slack OAuth failed: {exc}", severity="error")

    def _validate_connection(self) -> None:
        plugin_config = self._load_plugin_config()
        client = SlackClient(
            user_token=self.config.secrets.get(self._get_project_token_key()) or "",
            team_id=plugin_config.get("default_team_id"),
        )
        result = client.auth_test()

        match result:
            case ClientSuccess(data=auth):
                self._save_project_slack_config(
                    {
                        "default_team_id": auth.team_id,
                        "default_team_name": auth.team,
                        "granted_scopes": plugin_config.get("granted_scopes", []),
                        "default_channels": plugin_config.get("default_channels", []),
                    }
                )
                self._has_changes = True
                self.app.notify(
                    "Slack connection validated successfully.", severity="information"
                )
                self.dismiss(result=True)
            case ClientError(error_message=err):
                raise RuntimeError(err)

    def _disconnect(self) -> None:
        self.config.secrets.delete(self._get_project_token_key(), scope="user")
        self.config.secrets.delete(self._get_project_refresh_token_key(), scope="user")
        self.config.secrets.delete(self._get_project_token_expires_at_key(), scope="user")
        # Same reason as connecting: the token the plugin holds lives outside the
        # config files, so dropping it has to be announced explicitly.
        self.config.load(force_plugin_init=True)
        self._reconfigure_project_mode = False
        self._has_changes = True
        self.app.notify("Slack account disconnected for this project.", severity="information")
        self._refresh_view()

    def _remove_project_config(self) -> None:
        self.config.secrets.delete(self._get_project_token_key(), scope="user")
        self.config.secrets.delete(self._get_project_refresh_token_key(), scope="user")
        self.config.secrets.delete(self._get_project_token_expires_at_key(), scope="user")
        project_cfg_path = self.config.project_config_path
        if project_cfg_path and project_cfg_path.exists():
            with open(project_cfg_path, "rb") as f:
                project_data = tomli.load(f)

            plugins = project_data.get("plugins", {})
            if "slack" in plugins:
                del plugins["slack"]
            if not plugins and "plugins" in project_data:
                del project_data["plugins"]

            with open(project_cfg_path, "wb") as f:
                tomli_w.dump(project_data, f)

        self.config.load()
        self._reconfigure_project_mode = False
        self._has_changes = True
        self.app.notify("Slack project configuration removed.", severity="information")
        self._refresh_view()

    def _enable_reconfigure_project_mode(self) -> None:
        self._reconfigure_project_mode = True
        self._refresh_view()

    def action_go_back(self) -> None:
        self.dismiss(result=self._has_changes)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-button":
            self._start_oauth_flow()
        elif event.button.id == "validate-button":
            try:
                self._validate_connection()
            except Exception as exc:
                self.app.notify(f"Slack validation failed: {exc}", severity="error")
        elif event.button.id == "reconfigure-project-button":
            self._enable_reconfigure_project_mode()
        elif event.button.id == "disconnect-button":
            try:
                self._disconnect()
            except Exception as exc:
                self.app.notify(f"Failed to disconnect Slack account: {exc}", severity="error")
        elif event.button.id == "remove-project-config-button":
            try:
                self._remove_project_config()
            except Exception as exc:
                self.app.notify(f"Failed to remove Slack project config: {exc}", severity="error")
        elif event.button.id == "close-button":
            self.dismiss(result=self._has_changes)
