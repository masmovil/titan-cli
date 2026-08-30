"""
Search JIRA issues using custom JQL query
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..messages import msg
from ..utils import IssueSorter
from ..operations import substitute_jql_variables, build_issue_table_data


def search_jql_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Search JIRA issues using a custom JQL query.

    This is a generic search step that accepts raw JQL and allows variable substitution.
    Use this when you need a specific query that isn't covered by saved queries.

    Inputs (from ctx.data):
        jql (str): JQL query string (supports variable substitution with ${var_name})
        max_results (int, optional): Maximum number of results (default: 100)

    Outputs (saved to ctx.data):
        jira_issues (list): List of JiraTicket objects
        jira_issue_count (int): Number of issues found

    Returns:
        Success: Issues found
        Error: Search failed or JQL not provided

    Variable substitution:
        You can use ${variable_name} in the JQL and it will be replaced with values from ctx.data.
        Example: "project = ${project_key} AND fixVersion = ${fix_version}"

    Example usage in workflow:
        ```yaml
        - id: search_issues
          plugin: jira
          step: search_jql
          params:
            jql: "project = MYPROJECT AND status = 'In Progress' ORDER BY created DESC"
            max_results: 50

        # With variable substitution:
        - id: search_release
          plugin: jira
          step: search_jql
          params:
            jql: "project = ${project_key} AND fixVersion = ${fix_version} ORDER BY created DESC"
        ```
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Search JIRA Issues")

    if not ctx.jira:
        ctx.textual.error_text(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)
        ctx.textual.end_step("error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    # Get JQL query
    jql = ctx.get("jql")
    if not jql:
        error_msg = "JQL query is required but not provided"
        ctx.textual.error_text(error_msg)
        ctx.textual.dim_text("Provide 'jql' parameter in workflow step")
        ctx.textual.end_step("error")
        return Error(error_msg)

    # Perform variable substitution using operations
    jql = substitute_jql_variables(jql, ctx.data)

    # Show which query is being executed
    ctx.textual.text("")
    ctx.textual.bold_text("Executing JQL Query:")
    ctx.textual.dim_text(f"  {jql}")
    ctx.textual.text("")

    # Get max results
    max_results = ctx.get("max_results", 100)

    # Execute search with loading indicator
    # Request ALL fields including custom fields
    with ctx.textual.loading("Searching JIRA issues..."):
        result = ctx.jira.search_issues(jql=jql, max_results=max_results, fields=["*all"])

    # Pattern match on Result
    match result:
        case ClientSuccess(data=issues):
            if not issues:
                ctx.textual.dim_text("No issues found")
                ctx.textual.end_step("success")
                return Success(
                    "No issues found",
                    metadata={
                        "jira_issues": [],
                        "issues": [],  # Alias for compatibility
                        "jira_issue_count": 0
                    }
                )

            # Show results
            ctx.textual.text("")  # spacing
            ctx.textual.success_text(f"Found {len(issues)} issues")
            ctx.textual.text("")

            # Show detailed table
            ctx.textual.bold_text("Found Issues:")
            ctx.textual.text("")

            try:
                # Sort issues intelligently
                sorter = IssueSorter()
                sorted_issues = sorter.sort(issues)

                # Build table data using operations
                headers, rows = build_issue_table_data(sorted_issues, summary_max_length=60)

                ctx.interaction.table(
                    headers=headers,
                    rows=rows,
                    title=f"Issues (sorted by {sorter.get_sort_description()})",
                )

                # Use sorted issues for downstream steps
                issues = sorted_issues
            except Exception as e:
                # If table rendering fails, show error but continue with raw issue list
                ctx.textual.error_text(f"Error rendering table: {e}")
                ctx.textual.primary_text(f"Found {len(issues)} issues (showing raw data)")
                for i, issue in enumerate(issues, 1):
                    ctx.textual.text(f"{i}. {issue.key} - {issue.summary}")
                ctx.textual.text("")

            ctx.textual.end_step("success")
            return Success(
                f"Found {len(issues)} issues",
                metadata={
                    "jira_issues": issues,
                    "issues": issues,  # Alias for compatibility
                    "jira_issue_count": len(issues)
                }
            )

        case ClientError(error_message=err):
            error_msg = f"JIRA search failed: {err}"
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)


__all__ = ["search_jql_step"]
