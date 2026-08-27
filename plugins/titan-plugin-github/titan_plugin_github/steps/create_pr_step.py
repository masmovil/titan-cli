# plugins/titan-plugin-github/titan_plugin_github/steps/create_pr_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..messages import msg
from ..operations import determine_pr_assignees


def create_pr_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Creates a GitHub pull request using data from the workflow context.

    Requires:
        ctx.github: An initialized GitHubClient.
        ctx.git: An initialized GitClient.

    Inputs (from ctx.data):
        pr_title (str): The title of the pull request.
        pr_body (str, optional): The body/description of the pull request.
        pr_head_branch (str): The branch with the new changes.
        pr_base_branch (str, optional): The branch to merge into. Defaults to the git plugin's configured main branch.
        pr_is_draft (bool, optional): Whether to create the PR as a draft. Defaults to False.
        pr_reviewers (list, optional): List of GitHub usernames or team slugs to request review from.
        pr_excluded_reviewers (list, optional): List of GitHub usernames to exclude from team expansion.
        pr_labels (list, optional): List of label names to add to the PR.

    Configuration (from ctx.github.config):
        auto_assign_prs (bool): If True, automatically assigns the PR to the current GitHub user.

    Outputs (saved to ctx.data):
        pr_number (int): The number of the created pull request.
        pr_url (str): The URL of the created pull request.

    Returns:
        Success: If the PR is created successfully.
        Error: If any required context arguments are missing or if the API call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Create Pull Request")

    # 1. Get GitHub client from context
    if not ctx.github:
        ctx.textual.error_text("GitHub client is not available in the workflow context.")
        ctx.textual.end_step("error")
        return Error("GitHub client is not available in the workflow context.")
    if not ctx.git:
        ctx.textual.error_text("Git client is not available in the workflow context.")
        ctx.textual.end_step("error")
        return Error("Git client is not available in the workflow context.")

    # 2. Get required data from context and client config
    title = ctx.get("pr_title")
    body = ctx.get("pr_body")
    base = ctx.get("pr_base_branch") or ctx.git.main_branch
    head = ctx.get("pr_head_branch")
    is_draft = ctx.get("pr_is_draft", False)  # Default to not a draft

    missing = [
        name
        for name, value in (("pr_title", title), ("pr_head_branch", head))
        if not value
    ]
    if not base:
        missing.append("pr_base_branch (or git plugin 'main_branch' config)")

    if missing:
        error_msg = f"Missing required context for creating a pull request: {', '.join(missing)}."
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    # 3. Determine assignees if auto-assign is enabled
    assignees = ctx.get("pr_assignees")
    if not assignees and ctx.github.config.auto_assign_prs:
        result = ctx.github.get_current_user()
        match result:
            case ClientSuccess(data=current_user):
                assignees = determine_pr_assignees(
                    auto_assign=True,
                    current_user=current_user,
                    existing_assignees=assignees
                )
            case ClientError(error_message=err):
                # Log warning but continue without assignee
                ctx.textual.warning_text(f"Could not get current user for auto-assign: {err}")

    # Get reviewers from context (if provided)
    reviewers = ctx.get("pr_reviewers")

    # Get excluded reviewers from context (if provided)
    excluded_reviewers = ctx.get("pr_excluded_reviewers")

    # Get labels from context (if provided)
    labels = ctx.get("pr_labels")

    # 4. Call the client method
    ctx.textual.dim_text(f"Creating pull request '{title}' from {head} to {base}...")
    result = ctx.github.create_pull_request(
        title=title, body=body, base=base, head=head, draft=is_draft,
        assignees=assignees, reviewers=reviewers, labels=labels,
        excluded_reviewers=excluded_reviewers
    )

    match result:
        case ClientSuccess(data=pr):
            ctx.textual.text("")  # spacing
            ctx.textual.success_text(msg.GitHub.PR_CREATED.format(number=pr.number, url=pr.url))

            # Return Success with PR info
            ctx.textual.end_step("success")
            return Success(
                "Pull request created successfully.",
                metadata={"pr_number": pr.number, "pr_url": pr.url},
            )
        case ClientError(error_message=error_msg):
            # Check for common errors and provide helpful guidance
            if "No commits between" in error_msg or "Head sha can't be blank" in error_msg:
                ctx.textual.error_text(f"Failed to create pull request: {error_msg}")
                ctx.textual.text("")
                ctx.textual.warning_text("💡 The branch might not be pushed to the remote repository.")
                ctx.textual.text("")
                ctx.textual.dim_text("To fix this, push your branch and try again:")
                ctx.textual.dim_text(f"  git push -u origin {head}")
                ctx.textual.text("")
            else:
                ctx.textual.error_text(f"Failed to create pull request: {error_msg}")

            ctx.textual.end_step("error")
            return Error(f"Failed to create pull request: {error_msg}")
