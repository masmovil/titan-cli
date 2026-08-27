"""Pure operations for Slack target resolution and filtering."""

from __future__ import annotations

import unicodedata

from ..models import UISlackChannel, UISlackTarget, UISlackUser


def normalize_search_query(query: str) -> str:
    """Normalize a free-text query for user or channel filtering."""
    collapsed = " ".join(query.strip().lower().split())
    return "".join(
        char for char in unicodedata.normalize("NFKD", collapsed) if not unicodedata.combining(char)
    )


def _score_match(query: str, *candidates: str) -> int | None:
    """Score a normalized query against one or more normalized candidate strings."""
    best_score: int | None = None
    for candidate in candidates:
        if not candidate:
            continue
        if candidate == query:
            score = 0
        elif candidate.startswith(query):
            score = 1
        elif query in candidate:
            score = 2
        else:
            continue
        if best_score is None or score < best_score:
            best_score = score
    return best_score


def filter_users_for_query(
    users: list[UISlackUser], query: str, limit: int = 20
) -> list[UISlackUser]:
    """Return the best matching Slack users for a free-text query."""
    normalized_query = normalize_search_query(query)
    ranked: list[tuple[int, str, UISlackUser]] = []

    for user in users:
        name = normalize_search_query(user.name)
        real_name = normalize_search_query(user.real_name or "")
        score = _score_match(normalized_query, name, real_name)
        if score is None:
            continue
        ranked.append((score, real_name or name, user))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].id))
    return [user for _, _, user in ranked[:limit]]


def filter_channels_for_query(
    channels: list[UISlackChannel], query: str, limit: int = 20
) -> list[UISlackChannel]:
    """Return the best matching Slack channels for a free-text query."""
    normalized_query = normalize_search_query(query).lstrip("#")
    ranked: list[tuple[int, str, UISlackChannel]] = []

    for channel in channels:
        name = normalize_search_query(channel.name).lstrip("#")
        score = _score_match(normalized_query, name)
        if score is None:
            continue
        ranked.append((score, name, channel))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].id))
    return [channel for _, _, channel in ranked[:limit]]


def build_user_target(
    user: UISlackUser,
    team_id: str | None = None,
    connection_id: str | None = None,
) -> UISlackTarget:
    """Build the canonical Slack target model for a user target."""
    return UISlackTarget(
        target_type="user",
        target_id=user.id,
        target_name=user.real_name or user.name,
        team_id=team_id,
        connection_id=connection_id,
    )


def build_channel_target(
    channel: UISlackChannel,
    team_id: str | None = None,
    connection_id: str | None = None,
) -> UISlackTarget:
    """Build the canonical Slack target model for a channel target."""
    return UISlackTarget(
        target_type="channel",
        target_id=channel.id,
        target_name=channel.name,
        team_id=team_id,
        connection_id=connection_id,
    )
