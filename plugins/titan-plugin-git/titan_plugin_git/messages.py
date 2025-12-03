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
            git_client_not_available: str = "Git client is not available in the workflow context." # Reusing for consistency
            commit_message_required: str = "Commit message is required in ctx.data['commit_message']."
            commit_success: str = "Commit created successfully: {commit_hash}"
            client_error_during_commit: str = "Git client error during commit: {e}"
            command_failed_during_commit: str = "Git command failed during commit: {e}"
            unexpected_error_during_commit: str = "An unexpected error occurred during commit: {e}"

msg = Messages()
