"""
User-facing messages for JIRA plugin
"""


class Messages:
    """Container for all user-facing messages"""

    class Plugin:
        """Plugin-level messages"""
        CLIENT_INIT_WARNING: str = "Warning: JiraPlugin could not initialize JiraClient: {e}"
        CLIENT_NOT_AVAILABLE: str = "JiraPlugin not initialized or JIRA API not available."
        CLIENT_NOT_AVAILABLE_IN_CONTEXT: str = "JIRA client is not available in the workflow context."
        JIRA_CLIENT_NOT_AVAILABLE: str = "JIRA client not initialized. Please configure the plugin first."

    class Steps:
        """Step-level messages"""

        class Search:
            """Search issues step messages"""
            SEARCHING: str = "Searching JIRA issues with JQL: {jql}"
            SEARCH_SUCCESS: str = "Found {count} JIRA issue(s)"
            NO_RESULTS: str = "No JIRA issues found matching the query"
            SEARCH_FAILED: str = "Failed to search JIRA issues: {e}"
            QUERY_NOT_FOUND: str = "Saved query '{query_name}' not found."
            AVAILABLE_PREDEFINED: str = "Available predefined queries (first 15):"
            MORE_QUERIES: str = "  ... and {count} more"
            CUSTOM_QUERIES_HEADER: str = "Custom queries from config:"
            ADD_CUSTOM_HINT: str = "💡 Add custom queries to .titan/config.toml:"
            CUSTOM_QUERY_EXAMPLE: str = "[jira.saved_queries]\nmy_custom = \"assignee = currentUser() AND status != Done\""
            QUERY_NAME_REQUIRED: str = "query_name parameter is required"
            PROJECT_REQUIRED: str = (
                "Query '{query_name}' requires a 'project' parameter.\n"
                "JQL template: {jql}\n\n"
                "Provide it in workflow:\n"
                "  params:\n"
                "    query_name: \"{query_name}\"\n"
                "    project: \"PROJ\""
            )

        class GetIssue:
            """Get issue step messages"""
            GETTING_ISSUE: str = "Fetching JIRA issue: {issue_key}"
            GET_SUCCESS: str = "Retrieved JIRA issue: {issue_key}"
            GET_FAILED: str = "Failed to get JIRA issue: {e}"
            ISSUE_NOT_FOUND: str = "JIRA issue not found: {issue_key}"

        class CreateIssue:
            """Create issue step messages"""
            CREATING_ISSUE: str = "Creating JIRA issue: {summary}"
            CREATE_SUCCESS: str = "Created JIRA issue: {issue_key}"
            CREATE_FAILED: str = "Failed to create JIRA issue: {e}"
            MISSING_SUMMARY: str = "Issue summary is required"

        class UpdateStatus:
            """Update status step messages"""
            UPDATING_STATUS: str = "Updating JIRA issue {issue_key} to status: {status}"
            UPDATE_SUCCESS: str = "Updated JIRA issue {issue_key} to {status}"
            UPDATE_FAILED: str = "Failed to update JIRA issue status: {e}"
            INVALID_TRANSITION: str = "Cannot transition to '{status}'. Available: {transitions}"

        class AddComment:
            """Add comment step messages"""
            ADDING_COMMENT: str = "Adding comment to JIRA issue: {issue_key}"
            COMMENT_SUCCESS: str = "Added comment to JIRA issue {issue_key}"
            COMMENT_FAILED: str = "Failed to add comment: {e}"

        class LinkPR:
            """Link PR step messages"""
            LINKING_PR: str = "Linking PR to JIRA issue: {issue_key}"
            LINK_SUCCESS: str = "Linked PR to JIRA issue {issue_key}"
            LINK_FAILED: str = "Failed to link PR: {e}"

        class AIIssue:
            """AI issue generation step messages"""
            AI_NOT_CONFIGURED: str = "AI not configured. Run 'titan ai configure' to enable AI features."
            AI_NOT_CONFIGURED_SKIP: str = "AI not configured - skipping analysis"
            GENERATING_ISSUE: str = "Generating JIRA issue with AI..."
            GENERATION_SUCCESS: str = "AI generated JIRA issue successfully"
            GENERATION_FAILED: str = "AI generation failed: {e}"
            INVALID_ISSUE_TYPE: str = "Invalid issue type: {issue_type}. Use: bug, feature, or task"
            USER_REJECTED: str = "User rejected AI-generated issue"
            CONFIRM_USE_AI: str = "Use this AI-generated issue?"
            NO_ISSUE_FOUND: str = "No issue found to analyze"
            ANALYZING: str = "Analyzing issue with AI..."

        class ExtractKey:
            """Extract issue key step messages"""
            EXTRACTING_KEY: str = "Extracting JIRA key from branch: {branch}"
            KEY_FOUND: str = "Found JIRA key: {issue_key}"
            KEY_NOT_FOUND: str = "No JIRA key found in branch name: {branch}"
            INVALID_BRANCH_FORMAT: str = "Branch name doesn't follow pattern: feature/PROJ-123-description"

        class PromptSelectIssue:
            """Prompt select issue step messages"""
            NO_ISSUES_AVAILABLE: str = "No JIRA issues available to select from"
            NO_ISSUE_SELECTED: str = "No issue selected"
            UI_NOT_AVAILABLE: str = "UI not available for prompting"
            ASK_ISSUE_NUMBER: str = "Enter issue number to analyze"
            ISSUE_SELECTED: str = "Selected: {key} - {summary}"
            ISSUE_SELECTION_CONFIRM: str = "Selected: {key} - {summary}"
            SELECT_SUCCESS: str = "Selected issue: {key}"

    class JIRA:
        """JIRA-specific messages"""
        AUTHENTICATION_FAILED: str = "JIRA authentication failed. Check your API token."
        RATE_LIMIT_EXCEEDED: str = "JIRA API rate limit exceeded. Please wait and try again."
        NETWORK_ERROR: str = "Network error connecting to JIRA: {e}"
        INVALID_PROJECT: str = "Invalid JIRA project: {project}"
        INVALID_JQL: str = "Invalid JQL query: {jql}"


msg = Messages()

__all__ = ["msg", "Messages"]
