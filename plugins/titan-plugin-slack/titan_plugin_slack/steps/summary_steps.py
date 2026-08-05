"""Slack target resolution and AI summary steps."""

from titan_cli.ai.router.declaration import declare_ai_usage
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.ai.router.models import AIExecutionError, AIExecutionSuccess
from titan_cli.core.logging import get_logger
from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.ui.tui.widgets import OptionItem

from titan_cli.engine import Error, Skip, Success, WorkflowContext, WorkflowResult
from ..models import UISlackConversation, UISlackTarget
from ..operations import (
    build_summary_prompt,
    extract_identity_ids_from_messages,
    format_messages_as_transcript,
    sort_messages_chronologically,
    truncate_transcript_for_summary,
)


logger = get_logger(__name__)


MAX_COMBINED_TARGET_OPTIONS = 20
DEFAULT_SLACK_HISTORY_LIMIT = 30


def _summarization_error_message(error_text: str) -> str:
    """Convert an AI summary failure into a concise user-facing message."""
    normalized = error_text.lower()
    if (
        "429" in normalized
        or "rate limit" in normalized
        or "resource_exhausted" in normalized
        or "throttling_error" in normalized
    ):
        return (
            "AI summary is temporarily rate limited by the configured AI provider. "
            "Please wait and try again."
        )
    return f"AI summary failed: {error_text}"


def select_target_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Search both Slack users and channels for a single unified target selection.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        slack_target_query (str, optional): Query used to search both users and channels.
        slack_search_limit (int, optional): Maximum number of matches to keep from each search. Defaults to 10.
        slack_search_page_size (int, optional): Page size used while scanning Slack. Defaults to 1000.
        slack_search_max_pages (int, optional): Maximum pages to scan while searching. Defaults to 50.
        slack_exclude_archived (bool, optional): Whether to exclude archived channels. Defaults to True.

    Outputs (saved to ctx.data):
        slack_target (UISlackTarget): Canonical selected Slack target.
        slack_target_type (str): Selected target type (`user` or `channel`).
        slack_target_id (str): Slack target identifier.
        slack_target_name (str): User-facing target name.
        slack_target_query (str): Query used to resolve the selection.

    Returns:
        Success: If the unified target is selected successfully.
        Error: If Slack is unavailable, the query is invalid, the search fails, or no match is selected.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select Slack Target")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    raw_query = ctx.get("slack_target_query") or ctx.textual.ask_text(
        "Search Slack people or channels:", default=""
    )
    if not raw_query or len(raw_query.strip()) < 2:
        message = "Enter at least 2 characters to search Slack targets."
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    search_limit = ctx.get("slack_search_limit", 10)
    page_size = ctx.get("slack_search_page_size", 1000)
    max_pages = ctx.get("slack_search_max_pages", 50)
    exclude_archived = ctx.get("slack_exclude_archived", True)

    with ctx.textual.loading("Searching Slack users and channels..."):
        users_result = ctx.slack.search_users(
            raw_query,
            max_matches=search_limit,
            page_size=page_size,
            max_pages=max_pages,
        )
        channels_result = ctx.slack.search_channels(
            raw_query,
            max_matches=search_limit,
            page_size=page_size,
            max_pages=max_pages,
            exclude_archived=exclude_archived,
        )

    match users_result:
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)
        case ClientSuccess(data=users):
            pass

    match channels_result:
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)
        case ClientSuccess(data=channels):
            pass

    options = []
    for user in users:
        display_name = user.real_name or user.name or user.id
        options.append(
            OptionItem(
                value=UISlackTarget(
                    target_type="user",
                    target_id=user.id,
                    target_name=display_name,
                    team_id=ctx.get("slack_team_id"),
                    connection_id=ctx.get("slack_connection_id"),
                ),
                title=display_name,
                description=f"Person  @ {user.name} ({user.id})",
            )
        )
    for channel in channels:
        options.append(
            OptionItem(
                value=UISlackTarget(
                    target_type="channel",
                    target_id=channel.id,
                    target_name=channel.name,
                    team_id=ctx.get("slack_team_id"),
                    connection_id=ctx.get("slack_connection_id"),
                ),
                title=f"#{channel.name}",
                description=f"Channel  ({channel.id})",
            )
        )

    if not options:
        message = "No Slack users or channels matched that query."
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    selected = ctx.textual.ask_option(
        "Select the Slack target:",
        options=options[:MAX_COMBINED_TARGET_OPTIONS],
    )
    if not selected:
        message = "No Slack target was selected."
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    ctx.textual.success_text(
        f"Selected Slack {selected.target_type} target: {selected.target_name} ({selected.target_id})"
    )
    ctx.textual.end_step("success")
    return Success(
        f"Selected Slack {selected.target_type} target",
        metadata={
            "slack_target": selected,
            "slack_target_type": selected.target_type,
            "slack_target_id": selected.target_id,
            "slack_target_name": selected.target_name,
            "slack_target_query": raw_query,
        },
    )


def ensure_target_conversation_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Resolve a Slack conversation from the selected target.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        slack_target (UISlackTarget): Selected Slack target.

    Outputs (saved to ctx.data):
        slack_conversation (UISlackConversation): Resolved Slack conversation.
        slack_conversation_id (str): Conversation ID used for later operations.

    Returns:
        Success: If the target conversation is resolved successfully.
        Error: If Slack is unavailable, the target is missing, or the Slack request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Resolve Slack Conversation")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    target = ctx.get("slack_target")
    if not target:
        ctx.textual.error_text("Slack target not found in context")
        ctx.textual.end_step("error")
        return Error("Slack target not found in context")

    if target.target_type == "user":
        with ctx.textual.loading("Opening Slack direct message..."):
            result = ctx.slack.open_direct_message(target.target_id)
        match result:
            case ClientSuccess(data=conversation):
                pass
            case ClientError(error_message=err):
                ctx.textual.error_text(err)
                ctx.textual.end_step("error")
                return Error(err)
    elif target.target_type == "channel":
        conversation = UISlackConversation(
            id=target.target_id,
            is_im=False,
            team_id=target.team_id,
        )
    else:
        message = f"Unsupported Slack target type: {target.target_type}"
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    ctx.textual.success_text(
        f"Slack conversation ready: {conversation.id} for {target.target_name}"
    )
    ctx.textual.end_step("success")
    return Success(
        "Slack conversation ready",
        metadata={
            "slack_conversation": conversation,
            "slack_conversation_id": conversation.id,
        },
    )


def read_recent_messages_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Read the most recent messages from the resolved Slack conversation.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        slack_conversation_id (str): Slack conversation ID to read.
        slack_history_limit (int, optional): Number of recent messages to fetch. Defaults to 30.

    Outputs (saved to ctx.data):
        slack_messages (list[UISlackMessage]): Retrieved Slack messages.
        slack_user_display_names (dict[str, str]): Resolved Slack user display names keyed by user ID.
        slack_channel_display_names (dict[str, str]): Resolved Slack channel names keyed by channel ID.
        slack_messages_next_cursor (str | None): Pagination cursor for later reads.
        slack_messages_has_more (bool): Whether more messages are available.

    Returns:
        Success: If recent messages are retrieved successfully.
        Error: If Slack is unavailable, required context is missing, or the Slack request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Read Recent Slack Messages")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    conversation_id = ctx.get("slack_conversation_id")
    if not conversation_id:
        ctx.textual.error_text("Slack conversation ID not found in context")
        ctx.textual.end_step("error")
        return Error("Slack conversation ID not found in context")

    limit = ctx.get("slack_history_limit", DEFAULT_SLACK_HISTORY_LIMIT)

    with ctx.textual.loading("Reading recent Slack messages..."):
        result = ctx.slack.read_conversation(conversation_id, limit=limit)

    match result:
        case ClientSuccess(data=(messages, next_cursor, has_more)):
            messages = sort_messages_chronologically(messages)
            user_display_names: dict[str, str] = {}
            channel_display_names: dict[str, str] = {}
            user_ids, channel_ids = extract_identity_ids_from_messages(messages)

            for user_id in sorted(user_ids):
                resolved_user = ctx.slack.get_user(user_id)
                match resolved_user:
                    case ClientSuccess(data=user):
                        user_display_names[user_id] = user.real_name or user.name or user.id
                    case ClientError():
                        pass

            for channel_id in sorted(channel_ids):
                resolved_channel = ctx.slack.get_channel(channel_id)
                match resolved_channel:
                    case ClientSuccess(data=channel):
                        channel_display_names[channel_id] = channel.name or channel.id
                    case ClientError():
                        pass

            ctx.textual.success_text(f"Retrieved {len(messages)} Slack messages")
            ctx.textual.end_step("success")
            return Success(
                f"Retrieved {len(messages)} Slack messages",
                metadata={
                    "slack_messages": messages,
                    "slack_user_display_names": user_display_names,
                    "slack_channel_display_names": channel_display_names,
                    "slack_messages_next_cursor": next_cursor,
                    "slack_messages_has_more": has_more,
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)


@declare_ai_usage(
    task="slack_summary",
    # A transcript in, a summary out: a remote connection or a headless CLI can
    # serve it. Remote stays the default - there is no repo for a CLI to read
    # here, and it is markedly slower.
    executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
    preferred=[AIProviderType.REMOTE],
    enforces=True,
)
def ai_summarize_messages_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Summarize recent Slack messages with AI.

    Requires:
        ctx.textual: Textual UI context.

    Inputs (from ctx.data):
        slack_messages (list[UISlackMessage]): Messages to summarize.
        slack_target_name (str, optional): Human-facing target label for the summary.
        slack_summary_max_chars (int, optional): Maximum transcript size passed to AI. Defaults to 12000.

    Outputs (saved to ctx.data):
        slack_summary (str): AI-generated Slack summary.
        slack_summary_source_count (int): Number of source messages summarized.
        slack_summary_transcript_chars (int): Transcript size sent to AI after truncation.

    Returns:
        Success: If the summary is generated successfully.
        Skip: If AI is not configured or not available.
        Error: If messages are missing or the AI request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Summarize Slack Messages")

    if not ctx.ai_router:
        ctx.textual.dim_text("AI not configured - skipping Slack summary.")
        ctx.textual.end_step("skip")
        return Skip("AI not configured - skipping Slack summary.")

    messages = ctx.get("slack_messages")
    if not messages:
        ctx.textual.error_text("Slack messages not found in context")
        ctx.textual.end_step("error")
        return Error("Slack messages not found in context")

    target_name = ctx.get("slack_target_name")
    max_chars = ctx.get("slack_summary_max_chars", 12000)
    user_display_names = ctx.get("slack_user_display_names", {})
    channel_display_names = ctx.get("slack_channel_display_names", {})
    transcript = format_messages_as_transcript(
        messages,
        target_name=target_name,
        user_display_names=user_display_names,
        channel_display_names=channel_display_names,
    )
    transcript = truncate_transcript_for_summary(transcript, max_chars=max_chars)
    prompt = build_summary_prompt(target_name, transcript)

    with ctx.textual.loading("Summarizing Slack messages with AI..."):
        result = ctx.ai_router.generate_text(
            prompt,
            policy=ai_summarize_messages_step,
            max_tokens=1024,
            temperature=0.3,
        )

    match result:
        case AIExecutionSuccess(data=response_text):
            pass
        case AIExecutionError(error_code="AI_DISABLED", error_message=disabled_message):
            ctx.textual.dim_text(disabled_message)
            ctx.textual.end_step("skip")
            return Skip(disabled_message)
        case AIExecutionError(error_message=err):
            message = _summarization_error_message(err)
            logger.warning(
                "slack_summary_ai_request_failed",
                target_name=target_name,
                source_count=len(messages),
                transcript_chars=len(transcript),
                error=err,
            )
            ctx.textual.error_text(message)
            ctx.textual.end_step("error")
            return Error(message)

    summary = (response_text or "").strip()
    logger.info(
        "slack_summary_ai_response_received",
        target_name=target_name,
        source_count=len(messages),
        transcript_chars=len(transcript),
        response_chars=len(response_text or ""),
        summary_chars=len(summary),
    )
    if not summary:
        logger.warning(
            "slack_summary_ai_response_empty",
            target_name=target_name,
            source_count=len(messages),
            transcript_chars=len(transcript),
        )
        ctx.textual.error_text("AI returned an empty Slack summary.")
        ctx.textual.end_step("error")
        return Error("AI returned an empty Slack summary.")

    ctx.textual.markdown(summary)
    ctx.textual.end_step("success")
    return Success(
        "Slack summary generated",
        metadata={
            "slack_summary": summary,
            "slack_summary_source_count": len(messages),
            "slack_summary_transcript_chars": len(transcript),
        },
    )


__all__ = [
    "select_target_step",
    "ensure_target_conversation_step",
    "read_recent_messages_step",
    "ai_summarize_messages_step",
]
