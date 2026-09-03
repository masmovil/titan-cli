"""Reusable workflow steps for GitHub pull request operations."""

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext, WorkflowResult

from ..messages import msg


def get_pull_request_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Fetch a pull request and store it in workflow context.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to fetch.

    Outputs (saved to ctx.data):
        pr_info: The fetched pull request object.

    Returns:
        Success: If the pull request is fetched successfully.
        Error: If required context is missing or the GitHub call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Fetch Pull Request")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    with ctx.textual.loading(f"Fetching PR #{pr_number}..."):
        result = ctx.github.get_pull_request(int(pr_number))

    match result:
        case ClientSuccess(data=pr_info):
            ctx.textual.success_text(f"PR #{pr_info.number}: {pr_info.title}")
            ctx.textual.end_step("success")
            return Success(
                f"Fetched PR #{pr_info.number}",
                metadata={"pr_info": pr_info},
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch PR: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch PR: {err}")


def check_merge_queue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Check whether the pull request's base branch requires a merge queue.

    Lets a workflow announce the real outcome before merging: with a merge queue the
    PR is queued and merged later by GitHub, not merged on request.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to inspect.

    Outputs (saved to ctx.data):
        merge_queue_enabled (bool): Whether the base branch requires a merge queue.
        merge_queue_state: The merge queue state object, when the lookup succeeded.

    Returns:
        Success: When the PR number is available. A failed lookup is not fatal: it reports merge_queue_enabled=False so the workflow behaves as it always did.
        Error: If required context is missing.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Check Merge Queue")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    with ctx.textual.loading(f"Checking merge queue for PR #{pr_number}..."):
        result = ctx.github.get_merge_queue_state(int(pr_number))

    match result:
        case ClientSuccess(data=queue_state):
            if queue_state.is_merge_queue_enabled:
                ctx.textual.success_text(
                    "Merge queue required on the base branch - the queue decides the merge strategy"
                )
            else:
                ctx.textual.dim_text("No merge queue on the base branch - regular merge")

            ctx.textual.end_step("success")
            return Success(
                f"Merge queue enabled: {queue_state.is_merge_queue_enabled}",
                metadata={
                    "merge_queue_enabled": queue_state.is_merge_queue_enabled,
                    "merge_queue_state": queue_state,
                },
            )
        case ClientError(error_message=err):
            # Detection is a convenience, not a gate: never block a merge over it
            ctx.textual.warning_text(
                f"Could not check the merge queue: {err}. Continuing as if there were none."
            )
            ctx.textual.end_step("success")
            return Success(
                "Merge queue state unknown",
                metadata={"merge_queue_enabled": False},
            )


def merge_pull_request_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Merge a pull request, or add it to the base branch's merge queue.

    When the base branch requires a merge queue, GitHub owns the merge: the PR is
    queued and merged later by the queue instead of merged now. That is reported as a
    success, and told to later steps through `merge_queued` / `expected_pr_state`.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to merge.
        merge_method (str, optional): Merge strategy. Ignored with a merge queue.
        commit_title (str, optional): Override commit title. Ignored with a merge queue.
        commit_message (str, optional): Override commit message. Ignored with a merge queue.
        merge_queue_enabled (bool, optional): Result of a previous `check_merge_queue`, reused to avoid looking the queue up twice.

    Outputs (saved to ctx.data):
        merge_result: The GitHub merge result object.
        merge_queued (bool): True when the PR was added to the merge queue.
        expected_pr_state (str): "MERGED" after a regular merge, "OPEN" once queued.

    Returns:
        Success: If the pull request is merged or added to the merge queue.
        Error: If required context is missing or the GitHub call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Merge Pull Request")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    merge_method = ctx.get("merge_method", "squash")
    commit_title = ctx.get("commit_title")
    commit_message = ctx.get("commit_message")
    merge_queue_enabled = ctx.get("merge_queue_enabled")

    if merge_queue_enabled:
        loading_message = f"Adding PR #{pr_number} to the merge queue..."
    else:
        loading_message = f"Merging PR #{pr_number} with {merge_method}..."

    with ctx.textual.loading(loading_message):
        result = ctx.github.merge_pr(
            int(pr_number),
            merge_method=merge_method,
            commit_title=commit_title,
            commit_message=commit_message,
            merge_queue_enabled=merge_queue_enabled,
        )

    match result:
        case ClientSuccess(data=merge_result):
            if merge_result.queued:
                position = (
                    f" (position {merge_result.queue_position})"
                    if merge_result.queue_position is not None
                    else ""
                )
                ctx.textual.success_text(
                    f"PR #{pr_number} added to the merge queue{position} - "
                    "GitHub will merge it when the queue clears"
                )
                ctx.textual.end_step("success")
                return Success(
                    f"PR #{pr_number} added to the merge queue",
                    metadata={
                        "merge_result": merge_result,
                        "merge_queued": True,
                        "expected_pr_state": "OPEN",
                    },
                )

            if not merge_result.merged:
                ctx.textual.error_text(f"Failed to merge PR #{pr_number}: {merge_result.message}")
                ctx.textual.end_step("error")
                return Error(f"Failed to merge PR #{pr_number}: {merge_result.message}")

            ctx.textual.success_text(msg.GitHub.PR_MERGED.format(number=pr_number))
            ctx.textual.end_step("success")
            return Success(
                f"Merged PR #{pr_number}",
                metadata={
                    "merge_result": merge_result,
                    "merge_queued": False,
                    "expected_pr_state": "MERGED",
                },
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to merge PR: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to merge PR: {err}")


def verify_pull_request_state_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Verify a pull request is currently in the expected state.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to inspect.
        expected_state (str): Expected pull request state.

    Outputs (saved to ctx.data):
        verified_pr_info: The pull request object when verification succeeds.

    Returns:
        Success: If the pull request is in the expected state.
        Error: If required context is missing, verification fails, or the GitHub call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Verify Pull Request State")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    expected_state = ctx.get("expected_state")
    if not expected_state:
        ctx.textual.error_text("No expected PR state in context")
        ctx.textual.end_step("error")
        return Error("No expected PR state in context")

    expected_state = str(expected_state).upper()

    with ctx.textual.loading(f"Verifying PR #{pr_number} state..."):
        result = ctx.github.get_pull_request(int(pr_number))

    match result:
        case ClientSuccess(data=pr_info):
            actual_state = str(pr_info.state).upper()
            if actual_state != expected_state:
                ctx.textual.error_text(
                    f"PR #{pr_number} is {actual_state}, expected {expected_state}"
                )
                ctx.textual.end_step("error")
                return Error(
                    f"PR #{pr_number} state mismatch: expected {expected_state}, got {actual_state}"
                )

            ctx.textual.success_text(f"PR #{pr_number} is {actual_state}")
            ctx.textual.end_step("success")
            return Success(
                f"Verified PR #{pr_number} is {actual_state}",
                metadata={"verified_pr_info": pr_info},
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to verify PR state: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to verify PR state: {err}")


def verify_merge_outcome_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Verify the outcome of a merge that may have gone through a merge queue.

    A queued PR stays OPEN until the queue merges it, so verifying "MERGED" would
    fail for it. This step checks whatever the merge step actually did: the PR is
    merged, or it is sitting in the merge queue.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to inspect.
        merge_queued (bool, optional): Set by `merge_pull_request` when the PR was added to the merge queue.

    Outputs (saved to ctx.data):
        verified_pr_info: The pull request object, after a regular merge.
        merge_queue_state: The merge queue state, after a queued merge.

    Returns:
        Success: If the PR is merged, or still queued when it was enqueued.
        Error: If required context is missing, the PR is in neither state, or the GitHub call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Verify Merge Outcome")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    if not ctx.get("merge_queued"):
        # Regular merge: the PR must be MERGED right now
        with ctx.textual.loading(f"Verifying PR #{pr_number} was merged..."):
            result = ctx.github.get_pull_request(int(pr_number))

        match result:
            case ClientSuccess(data=pr_info):
                actual_state = str(pr_info.state).upper()
                if actual_state != "MERGED":
                    ctx.textual.error_text(f"PR #{pr_number} is {actual_state}, expected MERGED")
                    ctx.textual.end_step("error")
                    return Error(
                        f"PR #{pr_number} state mismatch: expected MERGED, got {actual_state}"
                    )

                ctx.textual.success_text(f"PR #{pr_number} is MERGED")
                ctx.textual.end_step("success")
                return Success(
                    f"Verified PR #{pr_number} is MERGED",
                    metadata={"verified_pr_info": pr_info},
                )
            case ClientError(error_message=err):
                ctx.textual.error_text(f"Failed to verify PR state: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to verify PR state: {err}")

    # Queued merge: in the queue, or already merged by it
    with ctx.textual.loading(f"Verifying PR #{pr_number} is in the merge queue..."):
        result = ctx.github.get_merge_queue_state(int(pr_number))

    match result:
        case ClientSuccess(data=queue_state):
            pr_state = str(queue_state.pr_state).upper()

            if pr_state == "MERGED":
                ctx.textual.success_text(f"PR #{pr_number} was already merged by the merge queue")
                ctx.textual.end_step("success")
                return Success(
                    f"Verified PR #{pr_number} was merged by the merge queue",
                    metadata={"merge_queue_state": queue_state},
                )

            if not queue_state.is_in_merge_queue:
                ctx.textual.error_text(
                    f"PR #{pr_number} is not in the merge queue and was not merged "
                    f"(state: {pr_state})"
                )
                ctx.textual.end_step("error")
                return Error(
                    f"PR #{pr_number} left the merge queue without being merged "
                    f"(state: {pr_state})"
                )

            ctx.textual.success_text(f"PR #{pr_number} is in the merge queue: {queue_state.summary}")
            ctx.textual.end_step("success")
            return Success(
                f"Verified PR #{pr_number} is in the merge queue",
                metadata={"merge_queue_state": queue_state},
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to verify the merge queue state: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to verify the merge queue state: {err}")


__all__ = [
    "get_pull_request_step",
    "check_merge_queue_step",
    "merge_pull_request_step",
    "verify_pull_request_state_step",
    "verify_merge_outcome_step",
]
