# plugins/titan-plugin-github/titan_plugin_github/steps/create_pr_step.py
from titan_cli.engine import WorkflowContext, Success, Error
from ..exceptions import GitHubAPIError

def create_pr_step(ctx: WorkflowContext) -> Success or Error:
    """
    Creates a GitHub pull request.

    This step retrieves the title, body, base branch, and head branch from the
    workflow context's data dictionary and uses the GitHub client to create a
    new pull request.

    Context Args:
        pr_title (str): The title of the pull request.
        pr_body (str): The body/description of the pull request.
        pr_base_branch (str): The branch to merge into (e.g., 'main', 'develop').
        pr_head_branch (str): The branch with the new changes.
        pr_is_draft (bool, optional): Whether to create the PR as a draft. Defaults to False.

    Returns:
        Success: If the PR is created successfully, with 'pr_number' and 'pr_url' in metadata.
        Error: If any required context arguments are missing or if the API call fails.
    """
    # 1. Get GitHub client from context
    if not ctx.github:
        return Error("GitHub client is not available in the workflow context.")

    # 2. Get required data from context
    title = ctx.get("pr_title")
    body = ctx.get("pr_body")
    base = ctx.get("pr_base_branch")
    head = ctx.get("pr_head_branch")
    is_draft = ctx.get("pr_is_draft", False) # Default to not a draft

    if not all([title, body, base, head]):
        return Error("Missing required context for creating a pull request: pr_title, pr_body, pr_base_branch, pr_head_branch.")

    # 3. Call the client method
    try:
        ctx.ui.text.info(f"Creating pull request: '{title}'")
        pr = ctx.github.create_pull_request(
            title=title,
            body=body,
            base=base,
            head=head,
            draft=is_draft
        )
        ctx.ui.text.success(f"Successfully created PR #{pr['number']}: {pr['url']}")

        # 4. Return Success with PR info
        return Success(
            f"Pull request #{pr['number']} created.",
            metadata={
                "pr_number": pr["number"],
                "pr_url": pr["url"]
            }
        )
    except GitHubAPIError as e:
        return Error(f"Failed to create pull request: {e}")
    except Exception as e:
        return Error(f"An unexpected error occurred while creating the pull request: {e}")
