"""Pure operations for formatting Slack messages for AI summaries."""

from __future__ import annotations

from datetime import datetime, timezone

from ..models import UISlackMessage
from .identity_resolution_operations import (
    build_message_author_label,
    replace_slack_mentions,
)


def sort_messages_chronologically(messages: list[UISlackMessage]) -> list[UISlackMessage]:
    """Order Slack messages oldest-first (Slack's history API returns newest-first)."""
    return sorted(messages, key=lambda message: float(message.ts))


def format_messages_as_transcript(
    messages: list[UISlackMessage],
    *,
    target_name: str | None = None,
    user_display_names: dict[str, str] | None = None,
    channel_display_names: dict[str, str] | None = None,
) -> str:
    """Format Slack messages as a compact transcript for downstream AI steps."""
    lines: list[str] = []
    if target_name:
        lines.append(f"Target: {target_name}")
        lines.append("")

    for message in messages:
        author = build_message_author_label(user_display_names or {}, message)
        text = replace_slack_mentions(
            message.text.strip(),
            user_display_names=user_display_names,
            channel_display_names=channel_display_names,
        )
        lines.append(
            f"[{_format_slack_timestamp(message.ts)}] {author}: {text}"
        )
    return "\n".join(lines).strip()


def truncate_transcript_for_summary(transcript: str, max_chars: int = 12000) -> str:
    """Truncate a transcript conservatively before sending it to AI."""
    if len(transcript) <= max_chars:
        return transcript
    marker = "[Transcript truncated]"
    if max_chars <= len(marker):
        return marker[:max_chars]
    prefix = transcript[: max_chars - len(marker) - 2].rstrip()
    return f"{prefix}\n\n{marker}"


def build_summary_prompt(target_name: str | None, transcript: str) -> str:
    """Build a reusable Slack summary prompt from transcript content."""
    target_label = target_name or "the selected Slack conversation"
    return (
        f"You are summarizing recent Slack activity in {target_label}.\n\n"
        "Write a concise, high-signal summary for someone who did not read the conversation. "
        "Prioritize substance over chronology and ignore low-value chatter unless it changes the outcome.\n\n"
        "Use exactly these sections and omit bullets only when there is truly nothing to report:\n"
        "Main topics:\n"
        "- 2 to 5 bullets covering the important discussion points or decisions\n\n"
        "Action items:\n"
        "- bullets in the form '<owner if known>: <next step>'\n"
        "- if no owner is visible, start with 'Unassigned:'\n"
        "- if there are no action items, write '- None'\n\n"
        "Open questions or blockers:\n"
        "- bullets for unresolved decisions, risks, or blockers\n"
        "- if there are none, write '- None'\n\n"
        "Notable context:\n"
        "- optional bullets for incidents, deadlines, links, or follow-up context that materially matter\n"
        "- if there is nothing notable, write '- None'\n\n"
        "Style rules:\n"
        "- Be specific and factual\n"
        "- Do not invent owners, intent, or decisions\n"
        "- Prefer short bullets over paragraphs\n"
        "- Keep the whole answer compact\n\n"
        "Transcript:\n"
        f"{transcript}"
    )


def _format_slack_timestamp(ts: str) -> str:
    """Render a Slack timestamp into a stable UTC label for transcript output."""
    try:
        timestamp = float(ts)
    except (TypeError, ValueError):
        return ts or "unknown-ts"
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
