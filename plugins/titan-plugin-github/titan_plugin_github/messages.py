# plugins/titan-plugin-github/titan_plugin_github/messages.py
class Messages:
    class Prompts:
        """Prompts specific to the GitHub plugin"""
        ENTER_PR_TITLE: str = "Enter Pull Request title:"
        ENTER_PR_BODY: str = "Enter PR body/description (press Meta+Enter or Esc then Enter to finish):"
        ENTER_PR_BODY_INFO: str = "Enter a description for your pull request. When you are finished, press Meta+Enter (or Esc followed by Enter)."

    class GitHub:
        """GitHub operations messages"""
        # Client errors
        CLI_NOT_FOUND: str = "GitHub CLI ('gh') not found. Please install it and ensure it's in your PATH."
        NOT_AUTHENTICATED: str = "GitHub CLI is not authenticated. Run: gh auth login"
        CONFIG_REPO_MISSING: str = "GitHub repository owner and name must be configured in [plugins.github.config]."
        API_ERROR: str = "GitHub API error: {error_msg}"
        PERMISSION_ERROR: str = "Permission denied for GitHub operation: {error_msg}"
        UNEXPECTED_ERROR: str = "An unexpected GitHub error occurred: {error}"

        # Pull Requests
        PR_NOT_FOUND: str = "Pull Request #{pr_number} not found."
        PR_CREATING: str = "Creating pull request..."
        PR_CREATED: str = "PR #{number} created: {url}"
        PR_UPDATED: str = "PR #{number} updated"
        PR_MERGED: str = "PR #{number} merged"
        PR_CLOSED: str = "PR #{number} closed"
        PR_FAILED: str = "Failed to create PR: {error}"
        PR_CREATION_FAILED: str = "Failed to create pull request: {error}"
        FAILED_TO_PARSE_PR_NUMBER: str = "Failed to parse PR number from URL: {url}"

        # Merge
        INVALID_MERGE_METHOD: str = "Invalid merge method: {method}. Must be one of: {valid_methods}"

        # Reviews
        REVIEW_NOT_FOUND: str = "Review ID #{review_id} for Pull Request #{pr_number} not found."
        REVIEW_CREATING: str = "Creating review..."
        REVIEW_CREATED: str = "Review submitted"
        REVIEW_FAILED: str = "Failed to submit review: {error}"

        # Comments
        COMMENT_CREATING: str = "Adding comment..."
        COMMENT_CREATED: str = "Comment added"
        COMMENT_FAILED: str = "Failed to add comment: {error}"

        # Repository
        REPO_NOT_FOUND: str = "Repository not found"
        REPO_ACCESS_DENIED: str = "Access denied to repository"

        # Authentication
        AUTH_MISSING: str = "GitHub token not found. Set GITHUB_TOKEN environment variable."
        AUTH_INVALID: str = "Invalid GitHub token"

        class AI:
            AI_NOT_CONFIGURED: str = "AI not configured. Run 'titan ai configure' to enable AI features."
            GITHUB_CLIENT_NOT_AVAILABLE: str = "GitHub client is not available in the workflow context."
            GIT_CLIENT_NOT_AVAILABLE: str = "Git client is not available in the workflow context."
            MISSING_PR_HEAD_BRANCH: str = "Missing pr_head_branch in context"
            ANALYZING_BRANCH_DIFF: str = "Analyzing branch diff: {head_branch} vs {base_branch}..."
            FAILED_TO_GET_BRANCH_DIFF: str = "Failed to get branch diff: {e}"
            NO_CHANGES_FOUND: str = "No changes found between branches"
            COMMITS_TRUNCATED: str = "\n  ... and {count} more commits"
            NO_DIFF_AVAILABLE: str = "No diff available"
            DIFF_TRUNCATED: str = "\n\n... (diff truncated for brevity)"
            PR_SIZE_INFO: str = "PR Size: {pr_size} ({files_changed} files, {diff_lines} lines) → Max description: {max_chars} chars"
            FAILED_TO_READ_PR_TEMPLATE: str = "Failed to read PR template: {e}"
            GENERATING_PR_DESCRIPTION: str = "Generating PR description with AI..."
            AI_RESPONSE_FORMAT_INCORRECT: str = "AI response format incorrect. Expected 'TITLE:' and 'DESCRIPTION:' sections.\nGot: {response_preview}..."
            AI_GENERATED_TRUNCATING: str = "AI generated {actual_len} chars, truncating to {max_chars}"
            AI_GENERATED_EMPTY_SHORT: str = "AI generated an empty or very short description."
            FULL_AI_RESPONSE: str = "Full AI response:"
            AI_GENERATED_INCOMPLETE: str = "AI generated an empty or incomplete PR description"
            AI_GENERATED_COMMIT_MESSAGE: str = "AI Generated Commit Message"
            COMMIT_MESSAGE_LABEL: str = "Commit Message:"
            CONFIRM_USE_AI_COMMIT: str = "Use this AI-generated commit message?"
            AI_COMMIT_REJECTED: str = "AI-generated commit message rejected"
            AI_GENERATED_PR_TITLE: str = "AI Generated PR:"
            TITLE_LABEL: str = "Title:"
            TITLE_TOO_LONG_WARNING: str = "Title is {length} chars (recommended: ≤72)"
            DESCRIPTION_LABEL: str = "Description:"
            CONFIRM_USE_AI_PR: str = "Use this AI-generated PR?"
            AI_SUGGESTION_REJECTED: str = "AI suggestion rejected. Will prompt for manual input."
            AI_GENERATED_PR_DESCRIPTION_SUCCESS: str = "AI generated PR description"
            AI_GENERATION_FAILED: str = "AI generation failed: {e}"
            FALLBACK_TO_MANUAL: str = "Falling back to manual PR creation..."

msg = Messages()
