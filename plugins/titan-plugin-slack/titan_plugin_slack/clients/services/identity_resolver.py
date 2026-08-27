"""Internal Slack identity resolver with simple in-memory caching."""

from titan_cli.core.result import ClientError, ClientSuccess, ClientResult

from ..sdk import SlackApiError
from ...models import NetworkSlackChannel, NetworkSlackUser, UISlackChannel, UISlackUser


class IdentityResolver:
    """Resolve Slack users and channels by ID with per-client caching."""

    def __init__(self, web_client):
        self._web_client = web_client
        self._user_cache: dict[str, UISlackUser] = {}
        self._channel_cache: dict[str, UISlackChannel] = {}

    @property
    def web_client(self):
        """Expose the underlying Slack WebClient."""
        return self._web_client

    @web_client.setter
    def web_client(self, value) -> None:
        """Replace the WebClient and invalidate caches tied to the old client."""
        self._web_client = value
        self._user_cache.clear()
        self._channel_cache.clear()

    @staticmethod
    def _map_user(member: dict) -> NetworkSlackUser:
        profile = member.get("profile", {})
        return NetworkSlackUser(
            id=member.get("id", ""),
            name=member.get("name", ""),
            real_name=(
                member.get("real_name")
                or profile.get("real_name")
                or profile.get("display_name")
            ),
            is_bot=member.get("is_bot", False),
            is_active=not member.get("deleted", False),
        )

    @staticmethod
    def _map_channel(channel: dict) -> NetworkSlackChannel:
        return NetworkSlackChannel(
            id=channel.get("id", ""),
            name=channel.get("name", ""),
            is_channel=channel.get("is_channel", True),
            is_private=channel.get("is_private", False),
        )

    @staticmethod
    def _to_ui_user(user: NetworkSlackUser) -> UISlackUser:
        return UISlackUser(
            id=user.id,
            name=user.name,
            real_name=user.real_name,
            is_bot=user.is_bot,
            is_active=user.is_active,
        )

    @staticmethod
    def _to_ui_channel(channel: NetworkSlackChannel) -> UISlackChannel:
        return UISlackChannel(
            id=channel.id,
            name=channel.name,
            is_channel=channel.is_channel,
            is_private=channel.is_private,
        )

    @staticmethod
    def _build_error(operation: str, exc_or_response, error_code: str) -> ClientError:
        response = getattr(exc_or_response, "response", exc_or_response)
        slack_error = "unknown_error"
        if isinstance(response, dict):
            slack_error = response.get("error", slack_error)
        elif hasattr(response, "data") and isinstance(response.data, dict):
            slack_error = response.data.get("error", slack_error)
        return ClientError(
            error_message=f"Slack {operation} failed: {slack_error}",
            error_code=error_code,
            details={"slack_error": slack_error},
        )

    def get_user(self, user_id: str) -> ClientResult[UISlackUser]:
        """Resolve a Slack user by ID, using cache when available."""
        if user_id in self._user_cache:
            return ClientSuccess(data=self._user_cache[user_id], message="Slack user resolved")

        try:
            response = self.web_client.users_info(user=user_id)
        except SlackApiError as exc:
            return self._build_error("get_user", exc, "GET_USER_ERROR")
        except Exception as exc:
            if hasattr(exc, "response"):
                return self._build_error("get_user", exc, "GET_USER_ERROR")
            return ClientError(
                error_message=f"Slack get_user request failed: {exc}",
                error_code="GET_USER_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            return self._build_error("get_user", response, "GET_USER_ERROR")

        user = self._to_ui_user(self._map_user(response.get("user", {})))
        self._user_cache[user_id] = user
        return ClientSuccess(data=user, message="Slack user resolved")

    def get_channel(self, channel_id: str) -> ClientResult[UISlackChannel]:
        """Resolve a Slack channel/conversation by ID, using cache when available."""
        if channel_id in self._channel_cache:
            return ClientSuccess(
                data=self._channel_cache[channel_id], message="Slack channel resolved"
            )

        try:
            response = self.web_client.conversations_info(channel=channel_id)
        except SlackApiError as exc:
            return self._build_error("get_channel", exc, "GET_CHANNEL_ERROR")
        except Exception as exc:
            if hasattr(exc, "response"):
                return self._build_error("get_channel", exc, "GET_CHANNEL_ERROR")
            return ClientError(
                error_message=f"Slack get_channel request failed: {exc}",
                error_code="GET_CHANNEL_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            return self._build_error("get_channel", response, "GET_CHANNEL_ERROR")

        channel = self._to_ui_channel(self._map_channel(response.get("channel", {})))
        self._channel_cache[channel_id] = channel
        return ClientSuccess(data=channel, message="Slack channel resolved")
