"""Internal service for Slack conversation history operations."""

from titan_cli.core.result import ClientError, ClientSuccess, ClientResult

from ..sdk import SlackApiError
from ...models import NetworkSlackMessage, UISlackConversation, UISlackMessage


class ConversationService:
    """Service for Slack conversation and history access."""

    @staticmethod
    def _extract_scope_context(response) -> tuple[str | None, str | None]:
        """Extract needed/provided scope context from Slack error responses."""
        if isinstance(response, dict):
            return response.get("needed"), response.get("provided")
        if hasattr(response, "data") and isinstance(response.data, dict):
            return response.data.get("needed"), response.data.get("provided")
        return None, None

    def __init__(self, web_client):
        self.web_client = web_client

    @staticmethod
    def _build_api_error(exc: SlackApiError, operation: str) -> ClientError:
        error_code = "unknown_error"
        response = getattr(exc, "response", None)
        needed, provided = ConversationService._extract_scope_context(response)
        if isinstance(response, dict):
            error_code = response.get("error", error_code)
        elif hasattr(response, "data") and isinstance(response.data, dict):
            error_code = response.data.get("error", error_code)
        message = f"Slack {operation} failed: {error_code}"
        details = {"slack_error": error_code}
        if error_code == "missing_scope" and needed:
            message += (
                f". Missing scopes: {needed}. "
                "Reconnect Slack configuration to grant the required scopes."
            )
            details["needed_scopes"] = needed
            if provided:
                details["provided_scopes"] = provided
        return ClientError(
            error_message=message,
            error_code="READ_CHANNEL_ERROR",
            details=details,
        )

    @staticmethod
    def _map_message(message: dict) -> NetworkSlackMessage:
        return NetworkSlackMessage(
            ts=message.get("ts", ""),
            text=message.get("text", ""),
            user=message.get("user"),
            bot_id=message.get("bot_id"),
            username=message.get("username"),
            thread_ts=message.get("thread_ts"),
            reply_count=message.get("reply_count", 0),
            subtype=message.get("subtype"),
        )

    @staticmethod
    def _to_ui_message(message: NetworkSlackMessage) -> UISlackMessage:
        return UISlackMessage(
            ts=message.ts,
            text=message.text,
            user=message.user,
            bot_id=message.bot_id,
            username=message.username,
            thread_ts=message.thread_ts,
            reply_count=message.reply_count,
            subtype=message.subtype,
        )

    def read_conversation(
        self,
        conversation_id: str,
        limit: int = 20,
        cursor: str | None = None,
        oldest: str | None = None,
        latest: str | None = None,
        inclusive: bool = False,
    ) -> ClientResult[tuple[list[UISlackMessage], str | None, bool]]:
        """Read message history from a Slack conversation."""
        try:
            response = self.web_client.conversations_history(
                channel=conversation_id,
                limit=limit,
                cursor=cursor,
                oldest=oldest,
                latest=latest,
                inclusive=inclusive,
            )
        except SlackApiError as exc:
            return self._build_api_error(exc, "read_channel")
        except Exception as exc:
            if hasattr(exc, "response"):
                return self._build_api_error(exc, "read_channel")
            return ClientError(
                error_message=f"Slack channel history request failed: {exc}",
                error_code="READ_CHANNEL_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            needed = response.get("needed")
            provided = response.get("provided")
            slack_error = response.get("error", "unknown_error")
            message = f"Slack read_channel failed: {slack_error}"
            details = {"slack_error": slack_error}
            if slack_error == "missing_scope" and needed:
                message += (
                    f". Missing scopes: {needed}. "
                    "Reconnect Slack configuration to grant the required scopes."
                )
                details["needed_scopes"] = needed
                if provided:
                    details["provided_scopes"] = provided
            return ClientError(
                error_message=message,
                error_code="READ_CHANNEL_ERROR",
                details=details,
            )

        messages = [self._map_message(message) for message in response.get("messages", [])]
        ui_messages = [self._to_ui_message(message) for message in messages]
        next_cursor = response.get("response_metadata", {}).get("next_cursor") or None
        has_more = response.get("has_more", False)
        return ClientSuccess(
            data=(ui_messages, next_cursor, has_more),
            message=f"Retrieved {len(ui_messages)} Slack messages",
        )

    def open_direct_message(self, user_id: str) -> ClientResult[UISlackConversation]:
        """Open or reuse a direct message conversation with the given user."""
        try:
            response = self.web_client.conversations_open(users=user_id, return_im=True)
        except SlackApiError as exc:
            built = self._build_api_error(exc, "open_direct_message")
            return ClientError(
                error_message=built.error_message,
                error_code="OPEN_DIRECT_MESSAGE_ERROR",
                details=built.details,
            )
        except Exception as exc:
            if hasattr(exc, "response"):
                built = self._build_api_error(exc, "open_direct_message")
                return ClientError(
                    error_message=built.error_message,
                    error_code="OPEN_DIRECT_MESSAGE_ERROR",
                    details=built.details,
                )
            return ClientError(
                error_message=f"Slack open_direct_message request failed: {exc}",
                error_code="OPEN_DIRECT_MESSAGE_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            needed = response.get("needed")
            provided = response.get("provided")
            slack_error = response.get("error", "unknown_error")
            message = f"Slack open_direct_message failed: {slack_error}"
            details = {"slack_error": slack_error}
            if slack_error == "missing_scope" and needed:
                message += (
                    f". Missing scopes: {needed}. "
                    "Reconnect Slack configuration to grant the required scopes."
                )
                details["needed_scopes"] = needed
                if provided:
                    details["provided_scopes"] = provided
            return ClientError(
                error_message=message,
                error_code="OPEN_DIRECT_MESSAGE_ERROR",
                details=details,
            )

        channel = response.get("channel") or {}
        return ClientSuccess(
            data=UISlackConversation(
                id=channel.get("id", ""),
                is_im=channel.get("is_im", True),
                user_id=channel.get("user") or user_id,
                team_id=channel.get("context_team_id"),
            ),
            message="Slack direct message conversation ready",
        )
