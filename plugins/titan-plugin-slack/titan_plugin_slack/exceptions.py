"""Custom exceptions for Slack plugin operations."""


class SlackError(Exception):
    """Base exception for Slack-related errors."""


class SlackConfigurationError(SlackError):
    """Slack plugin configuration is invalid or incomplete."""


class SlackClientError(SlackError):
    """Slack client is not initialized or cannot be used."""


class SlackAPIError(SlackError):
    """Slack API request failed."""
