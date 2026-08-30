# plugins/titan-plugin-git/titan_plugin_git/steps/diff_summary_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ports.protocol import InteractionOption
from titan_plugin_git.messages import msg
from ..operations import parse_diff_stat_output, expand_rename_path, colorize_diff_stats, colorize_diff_summary, format_diff_stat_display


def show_uncommitted_diff_summary(ctx: WorkflowContext) -> WorkflowResult:
    """
    Show uncommitted changes and let the user select which files to include
    in the commit. Each checkbox shows the filename and its diff stats inline.

    Saves selected file paths to ctx.data["selected_files"].

    Returns:
        Success: Files selected and saved to context
        Exit: No files selected by the user
        Skip: Could not retrieve diff stat
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.git:
        return Error(msg.Steps.Push.GIT_CLIENT_NOT_AVAILABLE)

    # Begin step container
    ctx.textual.begin_step("Show Changes Summary")

    result = ctx.git.get_uncommitted_diff_stat()

    match result:
        case ClientSuccess(data=stat_output):
            if not stat_output or not stat_output.strip():
                ctx.textual.dim_text("No uncommitted changes to show")
                ctx.textual.end_step("success")
                return Success("No changes")

            file_lines, summary_lines = parse_diff_stat_output(stat_output)

            if file_lines:
                max_len = max(len(filename) for filename, _ in file_lines)
                options = [
                    InteractionOption(
                        id=expand_rename_path(filename),
                        value=expand_rename_path(filename),
                        label=f"{filename.ljust(max_len)} |{colorize_diff_stats(stats)}",
                        badges=["selected"],
                    )
                    for filename, stats in file_lines
                ]

                summary_text = colorize_diff_summary(summary_lines[0].strip()) if summary_lines else ""
                question = f"Select files to include in the commit:  {summary_text}"

                selected = ctx.textual.ask_multiselect(question, options)

                if not selected:
                    ctx.textual.warning_text("No files selected. Select at least one file to commit.")
                    ctx.textual.end_step("skip")
                    return Exit("No files selected for commit")

                ctx.data["selected_files"] = selected

                # Show what was selected
                selected_set = set(selected)
                selected_lines = [(f, s) for f, s in file_lines if f in selected_set]
                formatted_selected = [
                    f"{f.ljust(max_len)} |{colorize_diff_stats(s)}"
                    for f, s in selected_lines
                ]
                formatted_summary = [colorize_diff_summary(summary_lines[0].strip())] if summary_lines else []
                ctx.textual.show_diff_stat(formatted_selected, formatted_summary, "Files to commit:")

            ctx.textual.end_step("success")
            return Success("Diff summary displayed")

        case ClientError(error_message=err):
            ctx.textual.end_step("skip")
            return Skip(f"Could not show diff summary: {err}")


def show_branch_diff_summary(ctx: WorkflowContext) -> WorkflowResult:
    """
    Show summary of branch changes (git diff base...head --stat).

    Provides a visual overview of files changed between branches
    before generating PR descriptions.

    Inputs (from ctx.data):
        pr_head_branch (str): Head branch name

    Returns:
        Success: Always (even if no changes, for workflow continuity)
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Show Branch Changes Summary")

    if not ctx.git:
        ctx.textual.error_text(msg.Steps.Push.GIT_CLIENT_NOT_AVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.Steps.Push.GIT_CLIENT_NOT_AVAILABLE)

    head_branch = ctx.get("pr_head_branch")
    if not head_branch:
        ctx.textual.dim_text("No head branch specified")
        ctx.textual.end_step("skip")
        return Skip("No head branch specified")

    base_branch = ctx.git.main_branch
    remote = ctx.git.default_remote

    # Get diff stat between branches using ClientResult pattern
    result = ctx.git.get_branch_diff_stat(base_branch, head_branch)

    match result:
        case ClientSuccess(data=stat_output):
            if not stat_output or not stat_output.strip():
                ctx.textual.dim_text(f"No changes between {remote}/{base_branch} and {head_branch}")
                ctx.textual.end_step("success")
                return Success("No changes")

            # Format and render diff stat
            formatted_files, formatted_summary = format_diff_stat_display(stat_output)
            ctx.textual.show_diff_stat(
                formatted_files, formatted_summary,
                f"Changes in {head_branch} vs {remote}/{base_branch}:"
            )

            ctx.textual.end_step("success")
            return Success("Branch diff summary displayed")

        case ClientError(error_message=err):
            # Don't fail the workflow, just skip
            ctx.textual.warning_text(f"Could not show branch diff summary: {err}")
            ctx.textual.end_step("skip")
            return Skip(f"Could not show branch diff summary: {err}")


__all__ = ["show_uncommitted_diff_summary", "show_branch_diff_summary"]
