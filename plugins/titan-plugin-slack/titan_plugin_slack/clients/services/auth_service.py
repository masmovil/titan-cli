"""Internal service for Slack auth operations."""

from titan_cli.core.result import ClientError, ClientSuccess, ClientResult

from ..sdk import SlackApiError
from ...models import UISlackAuth


class AuthService:
    """Service for validating Slack authentication."""

    def __init__(self, web_client):
        self.web_client = web_client

    @staticmethod
    def _build_api_error(exc: SlackApiError, operation: str) -> ClientError:
        error_code = "unknown_error"
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            error_code = response.get("error", error_code)
        elif hasattr(response, "data") and isinstance(response.data, dict):
            error_code = response.data.get("error", error_code)
        return ClientError(
            error_message=f"Slack {operation} failed: {error_code}",
            error_code="AUTH_ERROR",
            details={"slack_error": error_code},
        )

    def auth_test(self) -> ClientResult[UISlackAuth]:
        """Validate the configured user token with Slack auth.test."""
        try:
            response = self.web_client.auth_test()
        except SlackApiError as exc:
            return self._build_api_error(exc, "auth")
        except Exception as exc:
            if hasattr(exc, "response"):
                return self._build_api_error(exc, "auth")
            return ClientError(
                error_message=f"Slack auth request failed: {exc}",
                error_code="AUTH_REQUEST_ERROR",
            )

        if not response.get("ok", False):
            error_code = response.get("error", "unknown_error")
            return ClientError(
                error_message=f"Slack auth failed: {error_code}",
                error_code="AUTH_ERROR",
                details={"slack_error": error_code},
            )

        return ClientSuccess(
            data=UISlackAuth(
                user_id=response.get("user_id"),
                user=response.get("user"),
                team_id=response.get("team_id"),
                team=response.get("team"),
                url=response.get("url"),
                bot_id=response.get("bot_id"),
            ),
            message="Slack auth validated",
        )
