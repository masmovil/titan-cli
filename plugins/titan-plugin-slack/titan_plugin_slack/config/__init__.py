"""Slack plugin config helpers."""


def build_project_slack_token_key(project_name: str | None) -> str:
    """Return the keyring key used for the current project's Slack token."""
    if not project_name:
        raise ValueError("Slack project token key requires a configured project name.")
    return f"{project_name}_slack_user_token"


def build_project_slack_refresh_token_key(project_name: str | None) -> str:
    """Return the keyring key used for the current project's Slack refresh token."""
    if not project_name:
        raise ValueError("Slack project refresh token key requires a configured project name.")
    return f"{project_name}_slack_refresh_token"


def build_project_slack_token_expires_at_key(project_name: str | None) -> str:
    """Return the keyring key used for the current project's Slack token expiry metadata."""
    if not project_name:
        raise ValueError("Slack project token expiry key requires a configured project name.")
    return f"{project_name}_slack_token_expires_at"


__all__ = [
    "build_project_slack_token_key",
    "build_project_slack_refresh_token_key",
    "build_project_slack_token_expires_at_key",
]
