"""Reusable operations for resolving Slack user and channel identities."""

from __future__ import annotations

import re

from ..models import UISlackMessage


USER_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")
CHANNEL_MENTION_RE = re.compile(r"<#([A-Z0-9]+)(?:\|[^>]+)?>")


def extract_identity_ids_from_messages(
    messages: list[UISlackMessage],
) -> tuple[set[str], set[str]]:
    """Extract unique Slack user and channel IDs referenced in messages."""
    user_ids: set[str] = set()
    channel_ids: set[str] = set()

    for message in messages:
        if message.user:
            user_ids.add(message.user)

        text = message.text or ""
        user_ids.update(USER_MENTION_RE.findall(text))
        channel_ids.update(CHANNEL_MENTION_RE.findall(text))

    return user_ids, channel_ids


def build_user_display_label(user_display_names: dict[str, str], user_id: str | None) -> str:
    """Return the preferred author label for a Slack user ID."""
    if not user_id:
        return "Unknown"
    return user_display_names.get(user_id, user_id)


def build_message_author_label(
    user_display_names: dict[str, str], message: UISlackMessage
) -> str:
    """Return the preferred author label for a Slack message, including bot/app authors."""
    if message.user:
        return build_user_display_label(user_display_names, message.user)
    if message.username:
        return message.username
    if message.bot_id:
        return user_display_names.get(message.bot_id, message.bot_id)
    return "Unknown"


def replace_slack_mentions(
    text: str,
    *,
    user_display_names: dict[str, str] | None = None,
    channel_display_names: dict[str, str] | None = None,
) -> str:
    """Replace Slack user and channel mention markup with readable labels."""
    user_display_names = user_display_names or {}
    channel_display_names = channel_display_names or {}

    def _replace_user(match: re.Match[str]) -> str:
        user_id = match.group(1)
        display_name = user_display_names.get(user_id)
        if not display_name:
            return f"@{user_id}"
        return f"@{display_name}"

    def _replace_channel(match: re.Match[str]) -> str:
        channel_id = match.group(1)
        display_name = channel_display_names.get(channel_id)
        if not display_name:
            return f"#{channel_id}"
        return f"#{display_name}"

    text = USER_MENTION_RE.sub(_replace_user, text)
    text = CHANNEL_MENTION_RE.sub(_replace_channel, text)
    return text
