"""Public Slack workflow steps for validation and read-only discovery."""

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext, WorkflowResult


def validate_connection_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Validate the configured Slack connection and expose identity metadata.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        None documented.

    Outputs (saved to ctx.data):
        slack_auth (UISlackAuth): Slack auth identity details from `auth_test()`.
        slack_team_id (str | None): Team identifier reported by Slack.
        slack_team_name (str | None): Team name reported by Slack.
        slack_user_id (str | None): User identifier reported by Slack.
        slack_user_name (str | None): User name reported by Slack.

    Returns:
        Success: If the Slack connection validates successfully.
        Error: If the Slack client is not available or the auth request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Validate Slack Connection")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    with ctx.textual.loading("Validating Slack connection..."):
        result = ctx.slack.auth_test()

    match result:
        case ClientSuccess(data=auth):
            ctx.textual.success_text(
                f"Connected to Slack team {auth.team or 'Unknown'} as {auth.user or auth.user_id or 'Unknown'}"
            )
            ctx.textual.end_step("success")
            return Success(
                "Slack connection validated",
                metadata={
                    "slack_auth": auth,
                    "slack_team_id": auth.team_id,
                    "slack_team_name": auth.team,
                    "slack_user_id": auth.user_id,
                    "slack_user_name": auth.user,
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)


def list_public_channels_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    List public Slack channels visible to the current token.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        slack_limit (int, optional): Maximum number of channels to request. Defaults to 100.
        slack_cursor (str, optional): Pagination cursor for the next page.
        slack_exclude_archived (bool, optional): Whether to exclude archived channels. Defaults to True.

    Outputs (saved to ctx.data):
        slack_channels (list[UISlackChannel]): Public channels returned by Slack.
        slack_channels_next_cursor (str | None): Pagination cursor for a later request.

    Returns:
        Success: If the channel list is retrieved successfully.
        Error: If the Slack client is not available or the Slack request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("List Slack Public Channels")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    limit = ctx.get("slack_limit", 100)
    cursor = ctx.get("slack_cursor")
    exclude_archived = ctx.get("slack_exclude_archived", True)

    with ctx.textual.loading("Loading Slack public channels..."):
        result = ctx.slack.list_public_channels(
            limit=limit,
            cursor=cursor,
            exclude_archived=exclude_archived,
        )

    match result:
        case ClientSuccess(data=(channels, next_cursor)):
            if not channels:
                ctx.textual.dim_text("No public Slack channels were returned.")
            else:
                ctx.textual.success_text(f"Found {len(channels)} public Slack channels")
                for channel in channels[:10]:
                    ctx.textual.text(f"- #{channel.name} ({channel.id})")
                if len(channels) > 10:
                    ctx.textual.dim_text(f"... and {len(channels) - 10} more")

            ctx.textual.end_step("success")
            return Success(
                f"Retrieved {len(channels)} public Slack channels",
                metadata={
                    "slack_channels": channels,
                    "slack_channels_next_cursor": next_cursor,
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)


def list_users_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    List Slack users visible to the current token.

    Requires:
        ctx.slack: An initialized SlackClient.

    Inputs (from ctx.data):
        slack_limit (int, optional): Maximum number of users to request. Defaults to 100.
        slack_cursor (str, optional): Pagination cursor for the next page.

    Outputs (saved to ctx.data):
        slack_users (list[UISlackUser]): Users returned by Slack.
        slack_users_next_cursor (str | None): Pagination cursor for a later request.

    Returns:
        Success: If the user list is retrieved successfully.
        Error: If the Slack client is not available or the Slack request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("List Slack Users")

    if not ctx.slack:
        ctx.textual.error_text("Slack client not available")
        ctx.textual.end_step("error")
        return Error("Slack client not available")

    limit = ctx.get("slack_limit", 100)
    cursor = ctx.get("slack_cursor")

    with ctx.textual.loading("Loading Slack users..."):
        result = ctx.slack.list_users(limit=limit, cursor=cursor)

    match result:
        case ClientSuccess(data=(users, next_cursor)):
            if not users:
                ctx.textual.dim_text("No Slack users were returned.")
            else:
                ctx.textual.success_text(f"Found {len(users)} Slack users")
                for user in users[:10]:
                    label = user.real_name or user.name or user.id
                    ctx.textual.text(f"- {label} ({user.id})")
                if len(users) > 10:
                    ctx.textual.dim_text(f"... and {len(users) - 10} more")

            ctx.textual.end_step("success")
            return Success(
                f"Retrieved {len(users)} Slack users",
                metadata={
                    "slack_users": users,
                    "slack_users_next_cursor": next_cursor,
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)


__all__ = [
    "validate_connection_step",
    "list_public_channels_step",
    "list_users_step",
]
