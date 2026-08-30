"""
Search JIRA issues using saved query from utils registry
"""

from contextlib import nullcontext

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..messages import msg
from ..utils import SAVED_QUERIES, IssueSorter
from ..operations import (
    merge_query_collections,
    build_query_not_found_message,
    format_jql_with_project,
    build_issue_table_data,
)


def search_saved_query_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Search JIRA issues using a saved query.

    Queries are predefined in utils.SAVED_QUERIES (from utils/saved_queries.py).
    Projects can override or add custom queries in .titan/config.toml under [jira.saved_queries].

    Inputs (from ctx.data):
        query_name (str): Name of saved query (e.g., "my_bugs", "team_bugs")
        project (str, optional): Project key for parameterized queries (e.g., "ECAPP")
        max_results (int, optional): Maximum number of results (default: 50)

    Outputs (saved to ctx.data):
        jira_issues (list): List of JiraTicket objects
        jira_issue_count (int): Number of issues found
        used_query_name (str): Name of the query that was used

    Returns:
        Success: Issues found
        Error: Query not found or search failed

    Available predefined queries (from utils):
        Personal: my_open_issues, my_bugs, my_in_review, my_in_progress
        Team: current_sprint, team_open, team_bugs, team_in_review
        Priority: critical_issues, high_priority, blocked_issues
        Time: updated_today, created_this_week, recent_bugs
        Status: todo_issues, in_progress_all, done_recently

    Example usage in workflow:
        ```yaml
        - id: search
          plugin: jira
          step: search_saved_query
          params:
            query_name: "my_bugs"

        # For queries with {project} parameter:
        - id: search_team
          plugin: jira
          step: search_saved_query
          params:
            query_name: "team_bugs"
            project: "ECAPP"
        ```
    """
    ui = ctx.textual or getattr(ctx, "interaction", None)
    if not ui:
        return Error("UI interaction context is not available for this step.")

    # Begin step container
    ui.begin_step("Search Open Issues")

    if not ctx.jira:
        ui.error_text(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)
        ui.end_step("error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    # Get query name
    query_name = ctx.get("query_name")
    if not query_name:
        ui.error_text(msg.Steps.Search.QUERY_NAME_REQUIRED)
        ui.end_step("error")
        return Error(msg.Steps.Search.QUERY_NAME_REQUIRED)

    # Get all predefined queries from utils
    predefined_queries = SAVED_QUERIES.get_all()

    # Get custom queries from config (if any)
    custom_queries = {}
    try:
        if hasattr(ctx, 'plugin_manager') and ctx.plugin_manager is not None:
            jira_plugin = ctx.plugin_manager.get_plugin('jira')
            if jira_plugin and hasattr(jira_plugin, '_config') and jira_plugin._config is not None:
                custom_queries = jira_plugin._config.saved_queries or {}
    except Exception:
        pass

    # Merge queries using operations (custom queries override predefined)
    all_queries = merge_query_collections(predefined_queries, custom_queries)

    # Look up the query
    if query_name not in all_queries:
        # Build helpful error message using operations
        error_msg = build_query_not_found_message(query_name, predefined_queries, custom_queries, max_predefined_shown=15)
        ui.error_text(error_msg)
        ui.end_step("error")
        return Error(error_msg)

    jql = all_queries[query_name]

    # Get parameters for query formatting
    project = ctx.get("project")

    # Try to use default project from JIRA client if not provided
    if not project and ctx.jira and hasattr(ctx.jira, 'project_key'):
        project = ctx.jira.project_key

    # Format query if it has parameters using operations
    jql, format_error = format_jql_with_project(jql, project)
    if format_error:
        error_msg = msg.Steps.Search.PROJECT_REQUIRED.format(query_name=query_name, jql=jql)
        ui.error_text(error_msg)
        ui.end_step("error")
        return Error(error_msg)

    # Show which query is being used
    is_custom = query_name in custom_queries
    source_label = "Custom" if is_custom else "Predefined"

    ui.text("")
    if hasattr(ui, "bold_text"):
        ui.bold_text(f"Using {source_label} Query: {query_name}")
    else:
        ui.text(f"Using {source_label} Query: {query_name}")
    ui.dim_text(f"  JQL: {jql}")
    ui.text("")

    # Get max results
    max_results = ctx.get("max_results", 50)

    # Execute search with loading indicator
    loading = ui.loading("Searching JIRA issues...") if hasattr(ui, "loading") else nullcontext()
    with loading:
        result = ctx.jira.search_issues(jql=jql, max_results=max_results)

    # Pattern match on Result
    match result:
        case ClientSuccess(data=issues):
            if not issues:
                ui.dim_text(f"No issues found for query: {query_name}")
                ui.end_step("success")
                return Success(
                    "No issues found",
                    metadata={
                        "jira_issues": [],
                        "jira_issue_count": 0,
                        "used_query_name": query_name
                    }
                )

            # Show results
            ui.text("")  # spacing
            ui.success_text(f"Found {len(issues)} issues")
            ui.text("")

            # Show detailed table
            if hasattr(ui, "bold_text"):
                ui.bold_text("Found Issues:")
            else:
                ui.text("Found Issues:")
            ui.text("")

            try:
                # Sort issues intelligently
                sorter = IssueSorter()
                sorted_issues = sorter.sort(issues)

                # Build table data using operations
                headers, rows = build_issue_table_data(sorted_issues, summary_max_length=60)

                ui.table(
                    headers=headers,
                    rows=rows,
                    title=f"Issues (sorted by {sorter.get_sort_description()})",
                )

                # Use sorted issues for downstream steps
                issues = sorted_issues
            except Exception as e:
                # If table rendering fails, show error but continue with raw issue list
                ui.error_text(f"Error rendering table: {e}")
                if hasattr(ui, "primary_text"):
                    ui.primary_text(f"Found {len(issues)} issues (showing raw data)")
                else:
                    ui.text(f"Found {len(issues)} issues (showing raw data)")
                for i, issue in enumerate(issues, 1):
                    ui.text(f"{i}. {issue.key} - {issue.summary}")
                ui.text("")

            ui.end_step("success")
            return Success(
                f"Found {len(issues)} issues using query: {query_name}",
                metadata={
                    "jira_issues": issues,
                    "jira_issue_count": len(issues),
                    "used_query_name": query_name
                }
            )

        case ClientError(error_message=err):
            error_msg = f"JIRA search failed: {err}"
            ui.error_text(error_msg)
            ui.end_step("error")
            return Error(error_msg)


__all__ = ["search_saved_query_step"]
