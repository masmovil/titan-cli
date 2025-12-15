"""
Search JIRA issues using saved query from utils registry
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from ..exceptions import JiraAPIError
from ..messages import msg
from ..utils import SAVED_QUERIES, IssueSorter


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
    if ctx.views:
        ctx.views.step_header("search_saved_query", ctx.current_step, ctx.total_steps)

    if not ctx.jira:
        if ctx.ui:
            ctx.ui.panel.print(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT, panel_type="error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    # Get query name
    query_name = ctx.get("query_name")
    if not query_name:
        if ctx.ui:
            ctx.ui.panel.print(msg.Steps.Search.QUERY_NAME_REQUIRED, panel_type="error")
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

    # Merge queries (custom queries override predefined)
    all_queries = {**predefined_queries, **custom_queries}

    # Look up the query
    if query_name not in all_queries:
        # Build helpful error message
        predefined_list = list(predefined_queries.keys())
        custom_list = list(custom_queries.keys())

        error_msg = msg.Steps.Search.QUERY_NOT_FOUND.format(query_name=query_name) + "\n\n"
        error_msg += msg.Steps.Search.AVAILABLE_PREDEFINED + "\n  "
        error_msg += "\n  ".join(predefined_list[:15])
        if len(predefined_list) > 15:
            error_msg += "\n" + msg.Steps.Search.MORE_QUERIES.format(count=len(predefined_list) - 15)

        if custom_list:
            error_msg += "\n\n" + msg.Steps.Search.CUSTOM_QUERIES_HEADER + "\n  "
            error_msg += "\n  ".join(custom_list)
        else:
            error_msg += "\n\n" + msg.Steps.Search.ADD_CUSTOM_HINT + "\n"
            error_msg += msg.Steps.Search.CUSTOM_QUERY_EXAMPLE

        if ctx.ui:
            ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)

    jql = all_queries[query_name]

    # Get parameters for query formatting
    project = ctx.get("project")

    # Format query if it has parameters
    if "{project}" in jql:
        if not project:
            # Try to use default project from JIRA client
            if ctx.jira and hasattr(ctx.jira, 'project_key'):
                project = ctx.jira.project_key

        if not project:
            error_msg = msg.Steps.Search.PROJECT_REQUIRED.format(query_name=query_name, jql=jql)
            if ctx.ui:
                ctx.ui.panel.print(error_msg, panel_type="error")
            return Error(error_msg)

        jql = jql.format(project=project)

    # Show which query is being used
    is_custom = query_name in custom_queries
    source_label = "Custom" if is_custom else "Predefined"

    if ctx.ui:
        ctx.ui.spacer.small()
        ctx.ui.text.subtitle(f"Using {source_label} Query: {query_name}")
        ctx.ui.text.body(f"  JQL: {jql}", style="dim")
        ctx.ui.spacer.small()

    # Get max results
    max_results = ctx.get("max_results", 50)

    try:
        # Execute search
        if ctx.ui:
            ctx.ui.text.info("Searching...")

        issues = ctx.jira.search_tickets(jql=jql, max_results=max_results)

        if not issues:
            if ctx.ui:
                ctx.ui.panel.print(
                    f"No issues found for query: {query_name}",
                    panel_type="info"
                )
                ctx.ui.spacer.small()
            return Success(
                "No issues found",
                metadata={
                    "jira_issues": [],
                    "jira_issue_count": 0,
                    "used_query_name": query_name
                }
            )

        # Show results
        if ctx.ui:
            ctx.ui.panel.print(
                f"Found {len(issues)} issues",
                panel_type="success"
            )
            ctx.ui.spacer.small()

            # Show detailed table
            ctx.ui.text.subtitle("Found Issues:")
            ctx.ui.spacer.small()

            try:
                # Sort issues intelligently
                sorter = IssueSorter()
                sorted_issues = sorter.sort(issues)

                # Prepare table data with row numbers for selection
                headers = ["#", "Key", "Status", "Summary", "Assignee", "Type", "Priority"]
                rows = []
                for i, issue in enumerate(sorted_issues, 1):
                    assignee = issue.assignee or "Unassigned"
                    status = issue.status or "Unknown"
                    priority = issue.priority or "Unknown"
                    issue_type = issue.issue_type or "Unknown"
                    summary = (issue.summary or "No summary")[:60]

                    rows.append([
                        str(i),
                        issue.key,
                        status,
                        summary,
                        assignee,
                        issue_type,
                        priority
                    ])

                # Render and print table
                ctx.ui.table.print_table(
                    headers=headers,
                    rows=rows,
                    title=f"Issues (sorted by {sorter.get_sort_description()})"
                )
                ctx.ui.spacer.small()

                # Use sorted issues for downstream steps
                issues = sorted_issues
            except Exception as e:
                # If table rendering fails, show error but continue with raw issue list
                ctx.ui.text.error(f"Error rendering table: {e}")
                ctx.ui.text.info(f"Found {len(issues)} issues (showing raw data)")
                for i, issue in enumerate(issues, 1):
                    ctx.ui.text.body(f"{i}. {issue.key} - {getattr(issue, 'summary', 'N/A')}")
                ctx.ui.spacer.small()

        return Success(
            f"Found {len(issues)} issues using query: {query_name}",
            metadata={
                "jira_issues": issues,
                "jira_issue_count": len(issues),
                "used_query_name": query_name
            }
        )

    except JiraAPIError as e:
        error_msg = f"JIRA search failed: {e}"
        if ctx.ui:
            ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        error_msg = f"Unexpected error: {e}\n\nTraceback:\n{error_detail}"
        if ctx.ui:
            ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)


__all__ = ["search_saved_query_step"]
