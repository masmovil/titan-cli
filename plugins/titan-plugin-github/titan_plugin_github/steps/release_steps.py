"""Reusable workflow steps for GitHub release selection."""

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Skip, Success, WorkflowContext, WorkflowResult
from titan_cli.ui.tui.widgets import OptionItem


def select_release_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    List published GitHub releases and select one to use as a notes source.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        github_release_limit (int, optional): Maximum number of releases to list. Defaults to 15.

    Outputs (saved to ctx.data):
        selected_release (UIRelease): Selected GitHub release, including its notes body.
        selected_release_tag (str): Tag name of the selected release.
        selected_release_notes (str): Release notes body of the selected release.
        selected_release_url (str): URL of the selected release.

    Returns:
        Success: If a release is selected successfully.
        Skip: If no published releases exist.
        Error: If the GitHub client is not available or the request fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select GitHub Release")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    limit = ctx.get("github_release_limit", 15)

    with ctx.textual.loading("Fetching GitHub releases..."):
        result = ctx.github.list_releases(limit=limit)

    match result:
        case ClientSuccess(data=releases):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)

    if not releases:
        ctx.textual.dim_text("No published GitHub releases found.")
        ctx.textual.end_step("skip")
        return Skip("No published GitHub releases found")

    options = [
        OptionItem(
            value=release.tag_name,
            title=release.title,
            description=release.published_at or release.url,
        )
        for release in releases
    ]

    selected_tag = ctx.textual.ask_option("Select a GitHub release:", options=options)
    if not selected_tag:
        ctx.textual.error_text("No release was selected.")
        ctx.textual.end_step("error")
        return Error("No release was selected.")

    with ctx.textual.loading(f"Fetching notes for {selected_tag}..."):
        release_result = ctx.github.get_release(selected_tag)

    match release_result:
        case ClientSuccess(data=release):
            ctx.textual.success_text(f"Selected release {release.tag_name}")
            ctx.textual.end_step("success")
            return Success(
                f"Selected GitHub release {release.tag_name}",
                metadata={
                    "selected_release": release,
                    "selected_release_tag": release.tag_name,
                    "selected_release_notes": release.body,
                    "selected_release_url": release.url,
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(err)


__all__ = ["select_release_step"]
