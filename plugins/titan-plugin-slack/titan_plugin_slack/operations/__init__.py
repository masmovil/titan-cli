"""Operations for reusable Slack target resolution."""

from .target_resolution_operations import (
    build_channel_target,
    build_user_target,
    filter_channels_for_query,
    filter_users_for_query,
    normalize_search_query,
)
from .identity_resolution_operations import (
    extract_identity_ids_from_messages,
    replace_slack_mentions,
    build_user_display_label,
    build_message_author_label,
)
from .message_summary_operations import (
    build_summary_prompt,
    format_messages_as_transcript,
    sort_messages_chronologically,
    truncate_transcript_for_summary,
)

__all__ = [
    "normalize_search_query",
    "filter_users_for_query",
    "filter_channels_for_query",
    "build_user_target",
    "build_channel_target",
    "extract_identity_ids_from_messages",
    "replace_slack_mentions",
    "build_user_display_label",
    "build_message_author_label",
    "format_messages_as_transcript",
    "sort_messages_chronologically",
    "truncate_transcript_for_summary",
    "build_summary_prompt",
]
