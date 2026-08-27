"""Slack SDK compatibility layer used by the Slack client and services."""

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler
except ImportError:  # pragma: no cover - exercised implicitly in repo-level tests
    class WebClient:  # type: ignore[override]
        """Small fallback used until the plugin dependency is installed."""

        def __init__(self, token: str, timeout: int | None = None, retry_handlers=None):
            self.token = token
            self.timeout = timeout
            self.retry_handlers = retry_handlers or []

    class SlackApiError(Exception):
        """Fallback Slack API error used when slack-sdk is unavailable."""

        def __init__(self, message: str, response=None):
            super().__init__(message)
            self.response = response

    class RateLimitErrorRetryHandler:  # type: ignore[override]
        """Fallback retry handler used when slack-sdk is unavailable."""

        def __init__(self, max_retry_count: int = 1):
            self.max_retry_count = max_retry_count


__all__ = ["WebClient", "SlackApiError", "RateLimitErrorRetryHandler"]
