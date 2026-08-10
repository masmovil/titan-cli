"""
Merge a branch into the current one, with AI-assisted conflict resolution.

The workflow never moves HEAD: it fetches the source branch and merges the
remote-tracking ref, so a failure at any point leaves the user on the branch
they started on.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ui.tui.widgets import OptionItem

from ..messages import msg
from ..models.view.merge import MergeStatus
from ..operations import (
    resolve_merge_source,
    build_merge_ref,
    build_conflict_resolution_prompt,
    format_merge_summary,
)


def resolve_merge_target(ctx: WorkflowContext) -> WorkflowResult:
    """
    Resolve which branch gets merged and verify the repo is ready for it.

    Requires:
        ctx.git: An initialized GitClient.
        ctx.textual: The Textual UI context.

    Inputs (from ctx.data):
        source_branch (str, optional): Branch to merge (defaults to the configured base branch)
        remote (str, optional): Remote name (default: "origin")

    Outputs (saved to ctx.data):
        source_branch (str): Resolved branch to merge
        target_branch (str): Branch receiving the merge
        remote (str): Remote name
        merge_ref (str): Ref that will be merged, e.g. "origin/develop"

    Returns:
        Success: Target resolved
        Exit: Working tree is dirty, nothing was touched
        Error: Git client unavailable or the branch cannot be resolved
    """
    if not ctx.textual:
        return Error(msg.Steps.Merge.TEXTUAL_NOT_AVAILABLE)

    ctx.textual.begin_step("Resolve Merge Target")

    if not ctx.git:
        ctx.textual.error_text(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)

    current_result = ctx.git.get_current_branch()
    match current_result:
        case ClientSuccess(data=current_branch):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(f"Failed to get current branch: {err}")

    source_branch, reason = resolve_merge_source(
        explicit_branch=ctx.get("source_branch"),
        main_branch=ctx.git.main_branch,
        current_branch=current_branch,
    )

    if reason:
        message = msg.Steps.Merge.NO_SOURCE_BRANCH.format(reason=reason)
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    # A merge on a dirty tree cannot be rolled back cleanly: once it conflicts,
    # MERGE_HEAD is set and stashed changes can no longer be restored safely.
    dirty_result = ctx.git.has_uncommitted_changes()
    match dirty_result:
        case ClientSuccess(data=True):
            ctx.textual.warning_text(msg.Steps.Merge.DIRTY_WORKING_TREE)
            ctx.textual.dim_text(msg.Steps.Merge.DIRTY_WORKING_TREE_HINT)
            ctx.textual.end_step("skip")
            return Exit(msg.Steps.Merge.DIRTY_WORKING_TREE)
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(f"Failed to check working tree: {err}")

    remote = ctx.get("remote", "origin")
    merge_ref = build_merge_ref(source_branch, remote)

    ctx.textual.bold_text(f"{merge_ref} → {current_branch}")

    ctx.textual.end_step("success")
    return Success(
        f"Merging {merge_ref} into {current_branch}",
        metadata={
            "source_branch": source_branch,
            "target_branch": current_branch,
            "remote": remote,
            "merge_ref": merge_ref,
        }
    )


def fetch_merge_source(ctx: WorkflowContext) -> WorkflowResult:
    """
    Fetch the source branch from the remote without moving HEAD.

    Requires:
        ctx.git: An initialized GitClient.
        ctx.textual: The Textual UI context.

    Inputs (from ctx.data):
        source_branch (str): Branch to fetch
        remote (str): Remote name

    Returns:
        Success: Remote-tracking ref updated
        Error: Fetch failed or required inputs are missing
    """
    if not ctx.textual:
        return Error(msg.Steps.Merge.TEXTUAL_NOT_AVAILABLE)

    ctx.textual.begin_step("Fetch Source Branch")

    if not ctx.git:
        ctx.textual.error_text(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)

    source_branch = ctx.get("source_branch")
    remote = ctx.get("remote", "origin")

    if not source_branch:
        ctx.textual.error_text("No source branch resolved")
        ctx.textual.end_step("error")
        return Error("No source branch resolved")

    with ctx.textual.loading(msg.Steps.Merge.FETCHING.format(remote=remote, branch=source_branch)):
        fetch_result = ctx.git.fetch(remote=remote, branch=source_branch)

    match fetch_result:
        case ClientSuccess():
            ctx.textual.success_text(f"✓ Fetched {remote}/{source_branch}")
            ctx.textual.end_step("success")
            return Success(f"Fetched {remote}/{source_branch}")
        case ClientError(error_message=err):
            message = msg.Steps.Merge.FETCH_FAILED.format(
                remote=remote, branch=source_branch, e=err
            )
            ctx.textual.error_text(message)
            ctx.textual.end_step("error")
            return Error(message)


def merge_source_branch(ctx: WorkflowContext) -> WorkflowResult:
    """
    Merge the fetched ref into the current branch.

    Conflicts are an expected outcome, not an error: the step reports them and
    publishes the context the conflict-resolution step consumes.

    Requires:
        ctx.git: An initialized GitClient.
        ctx.textual: The Textual UI context.

    Inputs (from ctx.data):
        merge_ref (str): Ref to merge, e.g. "origin/develop"
        target_branch (str): Branch receiving the merge

    Outputs (saved to ctx.data):
        merge_status (str): One of up_to_date / fast_forward / merged / conflicted
        merge_conflicts (list): Paths with unresolved conflicts (empty when clean)
        merge_conflict_context (str): Prompt for the AI CLI, only set on conflicts

    Returns:
        Success: Merge finished, cleanly or with conflicts to resolve
        Error: Git refused to start the merge
    """
    if not ctx.textual:
        return Error(msg.Steps.Merge.TEXTUAL_NOT_AVAILABLE)

    ctx.textual.begin_step("Merge")

    if not ctx.git:
        ctx.textual.error_text(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)

    merge_ref = ctx.get("merge_ref")
    target_branch = ctx.get("target_branch", "")

    if not merge_ref:
        ctx.textual.error_text("No merge ref resolved")
        ctx.textual.end_step("error")
        return Error("No merge ref resolved")

    with ctx.textual.loading(msg.Steps.Merge.MERGING.format(ref=merge_ref)):
        merge_result = ctx.git.merge(merge_ref, target_branch=target_branch)

    match merge_result:
        case ClientSuccess(data=result):
            pass
        case ClientError(error_message=err):
            message = msg.Steps.Merge.MERGE_FAILED.format(e=err)
            ctx.textual.error_text(message)
            ctx.textual.end_step("error")
            return Error(message)

    summary = format_merge_summary(result)
    ctx.textual.bold_text(summary[0])
    for line in summary[1:]:
        ctx.textual.dim_text(line)

    if not result.has_conflicts:
        ctx.textual.success_text("✓ Merge completed")
        ctx.textual.end_step("success")
        return Success(
            f"Merge completed ({result.status.value})",
            metadata={
                "merge_status": result.status.value,
                "merge_conflicts": [],
            }
        )

    ctx.textual.warning_text(msg.Steps.Merge.CONFLICTS_TITLE)
    for path in result.conflicted_files:
        ctx.textual.text(f"  {path}")

    prompt = build_conflict_resolution_prompt(
        conflicted_files=result.conflicted_files,
        source_ref=result.source_ref,
        target_branch=result.target_branch,
    )

    ctx.textual.end_step("success")
    return Success(
        f"Merge stopped with {len(result.conflicted_files)} conflicted files",
        metadata={
            "merge_status": result.status.value,
            "merge_conflicts": result.conflicted_files,
            "merge_conflict_context": prompt,
        }
    )


def complete_merge(ctx: WorkflowContext) -> WorkflowResult:
    """
    Finish a conflicted merge after the user resolved the conflicts.

    Stages everything and commits with the message git prepared. If conflicts
    remain, the user chooses between aborting and committing as-is.

    Requires:
        ctx.git: An initialized GitClient.
        ctx.textual: The Textual UI context.

    Inputs (from ctx.data):
        merge_status (str): Status published by merge_source_branch
        merge_commit_no_verify (bool, optional): Skip pre-commit and commit-msg
            hooks on the merge commit (default: True)

    Outputs (saved to ctx.data):
        merge_commit_sha (str): SHA of the merge commit

    Returns:
        Success: Merge committed
        Skip: Merge was already complete, nothing to do
        Exit: User aborted the merge
        Error: Staging or committing failed
    """
    if not ctx.textual:
        return Error(msg.Steps.Merge.TEXTUAL_NOT_AVAILABLE)

    ctx.textual.begin_step("Complete Merge")

    if not ctx.git:
        ctx.textual.error_text(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.Steps.Merge.GIT_CLIENT_NOT_AVAILABLE)

    if ctx.get("merge_status") != MergeStatus.CONFLICTED.value:
        ctx.textual.dim_text(msg.Steps.Merge.NO_MERGE_IN_PROGRESS)
        ctx.textual.end_step("skip")
        return Skip(msg.Steps.Merge.NO_MERGE_IN_PROGRESS)

    # The AI CLI may have committed the merge itself; nothing left to do then.
    in_progress_result = ctx.git.is_merge_in_progress()
    match in_progress_result:
        case ClientSuccess(data=False):
            ctx.textual.dim_text(msg.Steps.Merge.NO_MERGE_IN_PROGRESS)
            ctx.textual.end_step("skip")
            return Skip(msg.Steps.Merge.NO_MERGE_IN_PROGRESS)
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(f"Failed to check merge state: {err}")

    # Content, not the index: a file edited but not staged is still listed as
    # unmerged by git even though its conflict is gone.
    with ctx.textual.loading(msg.Steps.Merge.CHECKING_CONFLICTS):
        conflicts_result = ctx.git.get_unresolved_conflict_files()

    match conflicts_result:
        case ClientSuccess(data=remaining):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(err)
            ctx.textual.end_step("error")
            return Error(f"Failed to check conflicts: {err}")

    if remaining:
        ctx.textual.warning_text(
            msg.Steps.Merge.UNRESOLVED_CONFLICTS.format(count=len(remaining))
        )
        for path in remaining:
            ctx.textual.text(f"  {path}")

        choice = ctx.textual.ask_option(
            msg.Steps.Merge.ASK_UNRESOLVED,
            [
                OptionItem(
                    value="abort",
                    title=msg.Steps.Merge.OPTION_ABORT_TITLE,
                    description=msg.Steps.Merge.OPTION_ABORT_DESC,
                ),
                OptionItem(
                    value="force",
                    title=msg.Steps.Merge.OPTION_FORCE_TITLE,
                    description=msg.Steps.Merge.OPTION_FORCE_DESC,
                ),
            ],
        )

        if choice != "force":
            with ctx.textual.loading(msg.Steps.Merge.ABORTING):
                abort_result = ctx.git.abort_merge()

            match abort_result:
                case ClientSuccess():
                    ctx.textual.success_text(f"✓ {msg.Steps.Merge.MERGE_ABORTED}")
                    ctx.textual.end_step("skip")
                    return Exit(msg.Steps.Merge.MERGE_ABORTED)
                case ClientError(error_message=err):
                    message = msg.Steps.Merge.ABORT_FAILED.format(e=err)
                    ctx.textual.error_text(message)
                    ctx.textual.end_step("error")
                    return Error(message)

    with ctx.textual.loading(msg.Steps.Merge.STAGING):
        stage_result = ctx.git.stage_all()

    match stage_result:
        case ClientError(error_message=err):
            message = msg.Steps.Merge.STAGE_FAILED.format(e=err)
            ctx.textual.error_text(message)
            ctx.textual.end_step("error")
            return Error(message)
        case _:
            pass

    # Hooks are skipped by default: the commit carries git's own merge message,
    # and a hook failing here would leave the merge stopped with everything
    # staged. Projects that want them can set merge_commit_no_verify: false.
    no_verify = bool(ctx.get("merge_commit_no_verify", True))

    if not no_verify:
        ctx.textual.dim_text(msg.Steps.Merge.COMMIT_HOOKS_HINT)

    with ctx.textual.loading(msg.Steps.Merge.COMMITTING):
        continue_result = ctx.git.continue_merge(no_verify=no_verify)

    match continue_result:
        case ClientSuccess(data=sha):
            message = msg.Steps.Merge.MERGE_COMMITTED.format(sha=sha[:8])
            ctx.textual.success_text(f"✓ {message}")
            ctx.textual.end_step("success")
            return Success(message, metadata={"merge_commit_sha": sha})
        case ClientError(error_message=err):
            message = msg.Steps.Merge.CONTINUE_FAILED.format(e=err)
            ctx.textual.error_text(message)
            ctx.textual.end_step("error")
            return Error(message)


__all__ = [
    "resolve_merge_target",
    "fetch_merge_source",
    "merge_source_branch",
    "complete_merge",
]
