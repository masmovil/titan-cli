import time
from pathlib import Path
from typing import Callable, Optional

import tomli
import tomli_w

from titan_cli.core.config import TitanConfig
from titan_cli.core.logging import get_logger
from titan_cli.core.plugins.models import SlackPluginConfig
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.security import SecretBroker

from .clients.slack_client import SlackClient
from .config import (
    build_project_slack_refresh_token_key,
    build_project_slack_token_expires_at_key,
    build_project_slack_token_key,
)
from .exceptions import SlackClientError, SlackConfigurationError
from .oauth import SlackOAuthFlow, SlackOAuthResult
from .screens.slack_config_screen import SlackConfigScreen

logger = get_logger(__name__)


def _parse_expiry(raw: Optional[str]) -> Optional[int]:
    """Epoch seconds from the stored expiry, or None when absent/corrupt."""
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class SlackPlugin(TitanPlugin):
    """Titan CLI plugin for Slack operations."""

    TOKEN_REFRESH_MARGIN_SECONDS = 300

    @property
    def name(self) -> str:
        return "slack"

    @property
    def description(self) -> str:
        return "Provides Slack messaging and workspace integration."

    @property
    def dependencies(self) -> list[str]:
        return []

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """Extract Slack plugin configuration."""
        if "slack" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["slack"]
        return plugin_entry.config if hasattr(plugin_entry, "config") else {}

    def get_config_schema(self) -> dict:
        """Return JSON schema for Slack plugin configuration."""
        return SlackPluginConfig.model_json_schema()

    def has_custom_config_screen(self) -> bool:
        """Slack uses a dedicated configuration screen."""
        return True

    def create_config_screen(self, config: TitanConfig) -> SlackConfigScreen:
        """Create the Slack-specific configuration screen."""
        return SlackConfigScreen(config)

    def _save_project_slack_config(self, config: TitanConfig, updates: dict[str, object | None]) -> None:
        """Persist Slack project config updates."""
        project_cfg_path = config.project_config_path
        if not project_cfg_path:
            raise SlackConfigurationError("Slack configuration requires a project config path.")

        config_data = {}
        if project_cfg_path.exists():
            with open(project_cfg_path, "rb") as f:
                config_data = tomli.load(f)

        config_data.setdefault("config_version", getattr(config.config, "config_version", "1.0"))
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

        config.load()

    def _should_refresh_token(self, token_expires_at: int | None, has_refresh_token: bool) -> bool:
        """Return whether the current token should be refreshed before use."""
        if not has_refresh_token:
            return False
        if token_expires_at is None:
            return True
        return token_expires_at <= int(time.time()) + self.TOKEN_REFRESH_MARGIN_SECONDS

    def _persist_refreshed_tokens(
        self,
        config: TitanConfig,
        broker: SecretBroker,
        project_name: str,
        result: SlackOAuthResult,
        validated_config: SlackPluginConfig,
    ) -> None:
        """Persist refreshed Slack OAuth credentials and metadata."""
        token_key = build_project_slack_token_key(project_name)
        refresh_token_key = build_project_slack_refresh_token_key(project_name)
        token_expires_at_key = build_project_slack_token_expires_at_key(project_name)
        broker.store(token_key, result.access_token)
        if result.refresh_token:
            broker.store(refresh_token_key, result.refresh_token)
        if result.expires_in:
            broker.store(
                token_expires_at_key,
                str(int(time.time()) + result.expires_in),
            )

        self._save_project_slack_config(
            config,
            {
                "default_team_id": result.team_id or validated_config.default_team_id,
                "default_team_name": result.team_name or validated_config.default_team_name,
                "token_type": None,
                "token_expires_at": None,
                "granted_scopes": result.granted_scopes or validated_config.granted_scopes,
            },
        )

    def _make_token_refresher(
        self,
        config: TitanConfig,
        broker: SecretBroker,
        project_name: str,
    ) -> Callable[[], str]:
        """Build a callable that exchanges the stored refresh token for a new
        access token and persists the result, for use by both the proactive
        refresh below and the reactive refresh-and-retry in SlackClient.
        """

        def _refresh() -> str:
            refresh_token_key = build_project_slack_refresh_token_key(project_name)
            if not broker.exists(refresh_token_key):
                raise SlackConfigurationError(
                    f"No Slack refresh token available for project '{project_name}'. "
                    "Reconnect Slack for this repository."
                )

            plugin_config_data = self._get_plugin_config(config)
            validated_config = SlackPluginConfig(**plugin_config_data)
            if not validated_config.oauth_client_id:
                raise SlackConfigurationError(
                    "Slack token refresh requires an OAuth client ID in project configuration."
                )

            flow = SlackOAuthFlow(client_id=validated_config.oauth_client_id)
            # The stored refresh token crosses into the exchange call; what
            # comes back is a fresh credential from Slack's response, not a
            # value read out of the vault.
            refreshed = broker.create_client(
                refresh_token_key, flow.refresh_access_token
            )

            # Slack rotates the refresh token on every use: persisting immediately
            # replaces the one we just consumed so the next refresh (proactive or
            # reactive) doesn't retry with an already-invalidated token.
            self._persist_refreshed_tokens(
                config,
                broker,
                project_name,
                refreshed,
                validated_config,
            )
            return refreshed.access_token

        return _refresh

    def initialize(self, config: TitanConfig, broker: SecretBroker) -> None:
        """Initialize the Slack client using the current user's personal token."""
        plugin_config_data = self._get_plugin_config(config)
        if not plugin_config_data:
            raise SlackConfigurationError(
                "Slack is enabled for this project but no Slack project configuration was found. Configure Slack in this repository first."
            )

        validated_config = SlackPluginConfig(**plugin_config_data)

        project_name = config.get_project_name()
        token_key = build_project_slack_token_key(project_name)
        refresh_token_key = build_project_slack_refresh_token_key(project_name)
        token_expires_at_key = build_project_slack_token_expires_at_key(project_name)

        if not broker.exists(token_key):
            raise SlackConfigurationError(
                f"Slack user token not found for project '{project_name}'. Configure Slack for this repository first."
            )

        has_refresh_token = broker.exists(refresh_token_key)
        # The expiry timestamp lives next to the tokens but is metadata, not
        # a credential: deriving the int through the broker is fine.
        token_expires_at = broker.create_client(
            token_expires_at_key, _parse_expiry, required=False
        )

        token_refresher = (
            self._make_token_refresher(config, broker, project_name)
            if has_refresh_token
            else None
        )

        refreshed_token: Optional[str] = None
        if self._should_refresh_token(token_expires_at, has_refresh_token):
            try:
                refreshed_token = token_refresher()
                refreshed_config_data = self._get_plugin_config(config)
                validated_config = SlackPluginConfig(**refreshed_config_data)
            except Exception as exc:
                # Don't fail plugin initialization over a proactive refresh
                # failure (e.g. transient network error): fall back to the
                # current token and let SlackClient's reactive refresh-and-retry
                # handle it if the token turns out to actually be unusable.
                logger.warning(
                    "slack_proactive_token_refresh_failed",
                    error=str(exc),
                    project_name=project_name,
                )

        def _build_client(user_token: str) -> SlackClient:
            # A blank stored token (manual secrets.env edits, keyring damage)
            # would build a client that looks authenticated and fails later
            # as an opaque 401 — fail here with the actionable message.
            if not user_token or not user_token.strip():
                raise SlackConfigurationError(
                    "Stored Slack user token is empty. "
                    "Reconnect Slack for this repository."
                )
            return SlackClient(
                user_token=user_token,
                team_id=validated_config.default_team_id,
                default_channels=validated_config.default_channels,
                token_refresher=token_refresher,
            )

        if refreshed_token is not None:
            # Fresh from Slack's OAuth response, never read out of the vault.
            self._client = _build_client(refreshed_token)
        else:
            self._client = broker.create_client(token_key, _build_client)

    def is_available(self) -> bool:
        """Return whether the plugin has an initialized client."""
        return hasattr(self, "_client") and self._client is not None

    def get_client(self) -> SlackClient:
        """Return the initialized Slack client instance."""
        if not hasattr(self, "_client") or self._client is None:
            raise SlackClientError(
                "SlackPlugin not initialized. Slack client may not be available."
            )
        return self._client

    def get_steps(self) -> dict:
        """Return public workflow steps for the plugin."""
        from .steps import (
            ai_summarize_messages_step,
            ensure_target_conversation_step,
            format_markdown_message_step,
            list_public_channels_step,
            list_users_step,
            open_direct_message_step,
            prepare_message_destination_step,
            post_message_step,
            prompt_message_body_step,
            read_recent_messages_step,
            select_target_step,
            select_channel_target_step,
            select_default_or_search_channel_target_step,
            select_user_target_step,
            validate_connection_step,
        )

        return {
            "validate_connection": validate_connection_step,
            "list_public_channels": list_public_channels_step,
            "list_users": list_users_step,
            "select_user_target": select_user_target_step,
            "select_channel_target": select_channel_target_step,
            "select_default_or_search_channel_target": select_default_or_search_channel_target_step,
            "select_target": select_target_step,
            "prepare_message_destination": prepare_message_destination_step,
            "ensure_target_conversation": ensure_target_conversation_step,
            "read_recent_messages": read_recent_messages_step,
            "ai_summarize_messages": ai_summarize_messages_step,
            "open_direct_message": open_direct_message_step,
            "format_markdown_message": format_markdown_message_step,
            "prompt_message_body": prompt_message_body_step,
            "post_message": post_message_step,
        }

    @property
    def workflows_path(self) -> Optional[Path]:
        """Return the plugin workflows directory path."""
        return Path(__file__).parent / "workflows"
