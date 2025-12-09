from typing import Any

class Messages:
    class Prompts:
        ENTER_COMMIT_MESSAGE: str = "Enter commit message:"

    class Git:
        """Git operations messages"""
        CLI_NOT_FOUND: str = "Git CLI not found. Please install Git."
        NOT_A_REPOSITORY: str = "'{repo_path}' is not a git repository"
        COMMAND_FAILED: str = "Git command failed: {error_msg}"
        UNEXPECTED_ERROR: str = "An unexpected error occurred: {e}"
        UNCOMMITTED_CHANGES_OVERWRITE_KEYWORD: str = "would be overwritten"
        CANNOT_CHECKOUT_UNCOMMITTED_CHANGES: str = "Cannot checkout: uncommitted changes would be overwritten"
        MERGE_CONFLICT_KEYWORD: str = "Merge conflict"
        MERGE_CONFLICT_WHILE_UPDATING: str = "Merge conflict while updating branch '{branch}'"
        AUTO_STASH_MESSAGE: str = "titan-cli-auto-stash at {timestamp}"
        CANNOT_CHECKOUT_UNCOMMITTED_CHANGES_EXIST: str = "Cannot checkout {branch}: uncommitted changes exist"
        STASH_FAILED_BEFORE_CHECKOUT: str = "Failed to stash changes before checkout"
        SAFE_SWITCH_STASH_MESSAGE: str = "titan-cli-safe-switch: from {current} to {branch}"
        
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
        REPO_INIT = "Initializing git repository..."
        REPO_INITIALIZED = "Git repository initialized"
    
    class Steps:
        class Status:
            GIT_CLIENT_NOT_AVAILABLE: str = "Git client is not available in the workflow context."
            STATUS_RETRIEVED_SUCCESS: str = "Git status retrieved successfully."
            STATUS_RETRIEVED_WITH_UNCOMMITTED: str = "Git status retrieved. Working directory is not clean."
            WORKING_DIRECTORY_NOT_CLEAN: str = " Working directory is not clean."
            WORKING_DIRECTORY_IS_CLEAN: str = "Git status retrieved. Working directory is clean."
            FAILED_TO_GET_STATUS: str = "Failed to get git status: {e}"

        class Commit:
            GIT_CLIENT_NOT_AVAILABLE: str = "Git client is not available in the workflow context."
            COMMIT_MESSAGE_REQUIRED: str = "Commit message cannot be empty."
            COMMIT_SUCCESS: str = "Commit created successfully: {commit_hash}"
            CLIENT_ERROR_DURING_COMMIT: str = "Git client error during commit: {e}"
            COMMAND_FAILED_DURING_COMMIT: str = "Git command failed during commit: {e}"
            UNEXPECTED_ERROR_DURING_COMMIT: str = "An unexpected error occurred during commit: {e}"
            WORKING_DIRECTORY_CLEAN: str = "Working directory is clean, skipping commit."
            NO_COMMIT_MESSAGE: str = "No commit message provided, skipping commit."

        class Push:
            GIT_CLIENT_NOT_AVAILABLE: str = "Git client is not available in the workflow context."
            PUSH_FAILED: str = "Git push failed: {e}"

        class Branch:
            GET_CURRENT_BRANCH_SUCCESS: str = "Current branch is '{branch}'"
            GET_CURRENT_BRANCH_FAILED: str = "Failed to get current branch: {e}"
            GET_BASE_BRANCH_SUCCESS: str = "Base branch is '{branch}'"
            GET_BASE_BRANCH_FAILED: str = "Failed to get base branch: {e}"

        class Prompt:
            WORKING_DIRECTORY_CLEAN: str = "Working directory is clean, no need for a commit message."
            COMMIT_MESSAGE_CAPTURED: str = "Commit message captured"
            USER_CANCELLED: str = "User cancelled."
            PROMPT_FAILED: str = "Failed to prompt for commit message: {e}"

        class AICommitMessage:
            AI_NOT_CONFIGURED: str = "AI not configured. Run 'titan ai configure' to enable AI features."
            NO_CHANGES_TO_COMMIT: str = "No changes to commit"
            ANALYZING_CHANGES: str = "📊 Analyzing uncommitted changes..."
            NO_UNCOMMITTED_CHANGES: str = "No uncommitted changes to analyze"
            DIFF_TRUNCATED: str = "... (diff truncated for brevity)"
            GENERATING_MESSAGE: str = "🤖 Generating commit message with AI..."
            GENERATED_MESSAGE_TITLE: str = "📝 AI Generated Commit Message:"
            MESSAGE_LENGTH_WARNING: str = "  ⚠️  Message is {length} chars (recommended: ≤72)"
            CONFIRM_USE_MESSAGE: str = "Use this commit message?"
            USER_DECLINED: str = "User declined AI-generated commit message"
            SUCCESS_MESSAGE: str = "AI generated commit message"
            GENERATION_FAILED: str = "AI generation failed: {e}"
            FALLBACK_TO_MANUAL: str = "Falling back to manual commit message..."
            GIT_CLIENT_NOT_AVAILABLE: str = "Git client is not available in the workflow context."

    class Plugin:
        GIT_CLIENT_INIT_WARNING: str = "Warning: GitPlugin could not initialize GitClient: {e}"
        GIT_CLIENT_NOT_AVAILABLE: str = "GitPlugin not initialized or Git CLI not available."



msg = Messages()
