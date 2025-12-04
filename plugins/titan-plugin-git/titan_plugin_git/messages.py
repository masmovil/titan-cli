from typing import Any

class Messages:
    class GitClient:
        cli_not_found: str = "Git CLI not found. Please install Git."
        not_a_repository: str = "'{repo_path}' is not a git repository"
        command_failed: str = "Git command failed: {error_msg}"
        unexpected_error: str = "An unexpected error occurred: {e}"
        branch_not_found: str = "Branch '{branch}' not found locally or on remote 'origin'"
        uncommitted_changes_overwrite_keyword: str = "would be overwritten"
        cannot_checkout_uncommitted_changes: str = "Cannot checkout: uncommitted changes would be overwritten"
        merge_conflict_keyword: str = "Merge conflict"
        merge_conflict_while_updating: str = "Merge conflict while updating branch '{branch}'"
        auto_stash_message: str = "titan-cli-auto-stash at {timestamp}"
        cannot_checkout_uncommitted_changes_exist: str = "Cannot checkout {branch}: uncommitted changes exist"
        stash_failed_before_checkout: str = "Failed to stash changes before checkout"
        safe_switch_stash_message: str = "titan-cli-safe-switch: from {current} to {branch}"
    
    class Steps:
        class Status:
            git_client_not_available: str = "Git client is not available in the workflow context."
            status_retrieved_success: str = "Git status retrieved successfully."
            working_directory_not_clean: str = " Working directory is not clean."
            failed_to_get_status: str = "Failed to get git status: {e}"

        class Commit:
            git_client_not_available: str = "Git client is not available in the workflow context."
            commit_message_required: str = "Commit message is required in ctx.data['commit_message']."
            commit_success: str = "Commit created successfully: {commit_hash}"
            client_error_during_commit: str = "Git client error during commit: {e}"
            command_failed_during_commit: str = "Git command failed during commit: {e}"
            unexpected_error_during_commit: str = "An unexpected error occurred during commit: {e}"

    class Plugin:
        git_client_init_warning: str = "Warning: GitPlugin could not initialize GitClient: {e}"
        git_client_not_available: str = "GitPlugin not initialized or Git CLI not available."

    class Git:
        """Git operations messages"""

        # Commits
        COMMITTING = "Committing changes..."
        COMMIT_SUCCESS = "Committed: {sha}"
        COMMIT_FAILED = "Commit failed: {error}"
        NO_CHANGES = "No changes to commit"

        # Branches
        BRANCH_CREATING = "Creating branch: {name}"
        BRANCH_CREATED = "Branch created: {name}"
        BRANCH_SWITCHING = "Switching to branch: {name}"
        BRANCH_SWITCHED = "Switched to branch: {name}"
        BRANCH_DELETING = "Deleting branch: {name}"
        BRANCH_DELETED = "Branch deleted: {name}"
        BRANCH_EXISTS = "Branch already exists: {name}"
        BRANCH_NOT_FOUND = "Branch not found: {name}"
        BRANCH_INVALID_NAME = "Invalid branch name: {name}"
        BRANCH_PROTECTED = "Cannot delete protected branch: {branch}"


        # Push/Pull
        PUSHING = "Pushing to remote..."
        PUSH_SUCCESS = "Pushed to {remote}/{branch}"
        PUSH_FAILED = "Push failed: {error}"
        PULLING = "Pulling from remote..."
        PULL_SUCCESS = "Pulled from {remote}/{branch}"
        PULL_FAILED = "Pull failed: {error}"

        # Status
        STATUS_CLEAN = "Working directory clean"
        STATUS_DIRTY = "Uncommitted changes detected"

        # Repository
        NOT_A_REPO = "Not a git repository"
        REPO_INIT = "Initializing git repository..."
        REPO_INITIALIZED = "Git repository initialized"


msg = Messages()
