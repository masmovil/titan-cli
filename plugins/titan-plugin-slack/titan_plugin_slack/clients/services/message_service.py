"""Internal service for Slack message posting operations."""

from titan_cli.core.result import ClientError, ClientSuccess, ClientResult

from ..sdk import SlackApiError
from ...models import UISlackPostedMessage


class MessageService:
    """Service for Slack message posting."""

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
        needed, provided = MessageService._extract_scope_context(response)
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
            error_code="POST_MESSAGE_ERROR",
            details=details,
        )

    def post_message(
        self,
        channel_id: str,
        text: str,
        *,
        thread_ts: str | None = None,
    ) -> ClientResult[UISlackPostedMessage]:
        """Post a plain-text Slack message to a conversation."""
        try:
            response = self.web_client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except SlackApiError as exc:
            return self._build_api_error(exc, "post_message")
        except Exception as exc:
            if hasattr(exc, "response"):
                return self._build_api_error(exc, "post_message")
            return ClientError(
                error_message=f"Slack post_message request failed: {exc}",
                error_code="POST_MESSAGE_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            needed = response.get("needed")
            provided = response.get("provided")
            slack_error = response.get("error", "unknown_error")
            message = f"Slack post_message failed: {slack_error}"
            details = {"slack_error": slack_error}
            if slack_error == "missing_scope" and needed:
                message += (
                    f". Missing scopes: {needed}. "
                    "Reconnect Slack configuration to grant the required scopes."
                )
                details["needed_scopes"] = needed
                details["provided_scopes"] = provided
            return ClientError(
                error_message=message,
                error_code="POST_MESSAGE_ERROR",
                details=details,
            )

        return ClientSuccess(
            data=UISlackPostedMessage(
                channel=response.get("channel", channel_id),
                ts=response.get("ts", ""),
                text=response.get("message", {}).get("text", text),
                thread_ts=response.get("message", {}).get("thread_ts") or thread_ts,
            ),
            message="Slack message posted",
        )
