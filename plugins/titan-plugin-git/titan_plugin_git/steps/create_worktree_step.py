# plugins/titan-plugin-git/titan_plugin_git/steps/create_worktree_step.py
"""
Step to create a temporary git worktree.

This allows working on a different branch without changing the current working directory.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
import tempfile


def create_worktree(ctx: WorkflowContext) -> WorkflowResult:
    """
    Create a temporary git worktree in detached HEAD mode from a remote base branch.

    This step creates a worktree in a temporary directory in detached HEAD state,
    pointing to the latest commit from the remote base branch. The base branch is
    resolved from the `base_branch` context variable when present, falling back to
    the git plugin's configured main branch. This allows creating a clean workspace
    even if you're currently on the base branch or have uncommitted changes.

    The worktree is created in detached HEAD mode, which means:
    - It doesn't conflict with your current branch
    - It works even if you're on the base branch with uncommitted changes
    - It always uses the latest code from the remote

    Inputs (from ctx.data):
        base_branch (str, optional): Base branch to create the worktree from. Defaults to the git plugin's configured main branch.
        path (str, optional): Custom path for the worktree. Defaults to a temporary directory.

    Outputs (saved to ctx.data):
        worktree_path (str): Path to the created worktree.
        base_branch (str): Base branch name (e.g., "develop", "main" or "rc/26.18.2").

    Returns:
        Success: If the worktree is created successfully.
        Error: If the Git client is unavailable, no base branch can be resolved, or worktree creation fails.

    Example:
        ```yaml
        - name: "Create Worktree"
          plugin: git
          step: create_worktree
          params:
            base_branch: "${base_branch}"
        ```
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step
    ctx.textual.begin_step("Create Worktree")

    try:
        from titan_cli.core.result import ClientSuccess, ClientError as ResultClientError

        # Get configuration: explicit base branch from context, fallback to main branch
        base_branch = ctx.get("base_branch") or ctx.git.main_branch
        remote = ctx.git.default_remote

        if not base_branch:
            error_msg = (
                "No base branch available to create the worktree: "
                "provide 'base_branch' in context or configure 'main_branch' in the git plugin."
            )
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)

        custom_path = ctx.get("path")

        # Determine worktree path
        if custom_path:
            worktree_path = custom_path
        else:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="titan-worktree-")
            worktree_path = temp_dir

        # Display info
        ctx.textual.text("")
        ctx.textual.primary_text(f"Creating worktree at: {worktree_path}")
        ctx.textual.dim_text(f"Base: {remote}/{base_branch} (detached HEAD)")

        # Fetch to ensure we have latest remote refs
        ctx.textual.text("")
        ctx.textual.dim_text(f"Fetching latest from {remote}...")

        fetch_result = ctx.git.fetch(remote=remote, branch=base_branch)
        match fetch_result:
            case ClientSuccess():
                ctx.textual.dim_text(f"✓ Fetched {remote}/{base_branch}")
            case ResultClientError(error_message=err):
                ctx.textual.warning_text(f"Fetch failed: {err}")
                ctx.textual.dim_text("Proceeding with local refs...")

        # Check if worktree already exists at the same path and remove it
        worktrees_result = ctx.git.list_worktrees()
        match worktrees_result:
            case ClientSuccess(data=existing_worktrees):
                import os
                main_repo_path = os.path.abspath(ctx.git.repo_path)

                for wt in existing_worktrees:
                    wt_path = wt.path

                    # Skip the main worktree (the actual repository directory)
                    if os.path.abspath(wt_path) == main_repo_path:
                        continue

                    # Remove if same path (we use detached HEAD so branch conflicts are no longer an issue)
                    if wt_path == worktree_path:
                        ctx.textual.text("")
                        ctx.textual.warning_text(f"Worktree already exists at: {wt_path}")
                        ctx.textual.dim_text("Removing existing worktree...")

                        remove_result = ctx.git.remove_worktree(path=wt_path, force=True)
                        match remove_result:
                            case ClientSuccess():
                                ctx.textual.dim_text("✓ Removed existing worktree")
                            case ResultClientError(error_message=err):
                                ctx.textual.dim_text(f"Warning: Could not remove worktree: {err}")
            case ResultClientError(error_message=err):
                ctx.textual.dim_text(f"Warning: Could not list worktrees: {err}")

        # Create worktree in detached HEAD mode from remote branch
        # This allows creating the worktree even if we're currently on the same branch
        ctx.textual.text("")
        remote_ref = f"{remote}/{base_branch}"

        create_wt_result = ctx.git.create_worktree(
            path=worktree_path,
            branch=remote_ref,
            create_branch=False,
            detached=True  # Detached HEAD - doesn't conflict with current branch
        )

        match create_wt_result:
            case ClientSuccess():
                # Success
                ctx.textual.text("")
                ctx.textual.success_text(f"✓ Created worktree at {worktree_path}")
            case ResultClientError(error_message=err):
                ctx.textual.text("")
                ctx.textual.error_text(f"Failed to create worktree: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to create worktree: {err}")

        ctx.textual.text("")
        ctx.textual.end_step("success")

        # Store in workflow variables
        return Success(
            f"Worktree created at {worktree_path}",
            metadata={
                "worktree_path": worktree_path,
                "base_branch": base_branch  # Save base branch for PR creation
            }
        )

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()

        ctx.textual.text("")
        ctx.textual.error_text(f"Failed to create worktree: {str(e)}")
        ctx.textual.text("")
        ctx.textual.dim_text("Traceback:")
        ctx.textual.dim_text(error_detail)

        ctx.textual.end_step("error")
        return Error(f"Failed to create worktree: {str(e)}")
