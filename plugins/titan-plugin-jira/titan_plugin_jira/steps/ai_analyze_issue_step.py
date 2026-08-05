"""
AI-powered JIRA issue analysis step
"""

from titan_cli.ai.router.declaration import declare_ai_usage
from titan_cli.ai.router.enums import AIProviderType, AITask
from titan_cli.ai.router.models import AIExecutionError, AIExecutionSuccess
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from ..messages import msg
from ..agents import JiraAgent
from ..formatters import IssueAnalysisMarkdownFormatter


@declare_ai_usage(
    task=AITask.JIRA_ANALYSIS,
    # JiraAgent makes several calls of its own; until a CLI-backed generator
    # exists, a remote connection is the only thing this code can drive.
    executes=[AIProviderType.REMOTE],
    enforces=True,
)
def ai_analyze_issue_requirements_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Analyze JIRA issue requirements using AI.

    Provides intelligent analysis of:
    - Summary and description breakdown
    - Acceptance criteria extraction
    - Technical requirements identification
    - Potential challenges and risks
    - Implementation suggestions
    - Missing information detection

    Inputs (from ctx.data):
        jira_issue (JiraTicket): JIRA issue object to analyze
        selected_issue (JiraTicket, optional): Alternative source

    Outputs (saved to ctx.data):
        ai_analysis (str): AI-generated analysis
        analysis_sections (dict): Structured analysis breakdown

    Returns:
        Success: If the issue analysis completes successfully.
        Skip: If AI is not configured or not available.
        Error: If no issue is available to analyze.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("AI Analyze Issue")

    # Use the connection the user chose for this task; the agent drives it.
    ai_client = ctx.ai
    if ctx.ai_router:
        match ctx.ai_router.resolve_remote_client(policy=ai_analyze_issue_requirements_step):
            case AIExecutionSuccess(data=resolved_client):
                ai_client = resolved_client
            case AIExecutionError(error_code="AI_DISABLED", error_message=disabled_message):
                ctx.textual.dim_text(disabled_message)
                ctx.textual.end_step("skip")
                return Skip(disabled_message)
            case AIExecutionError(error_message=err):
                ctx.textual.error_text(err)
                ctx.textual.end_step("error")
                return Error(err)

    if not ai_client or not ai_client.is_available():
        ctx.textual.dim_text(msg.Steps.AIIssue.AI_NOT_CONFIGURED_SKIP)
        ctx.textual.end_step("skip")
        return Skip(msg.Steps.AIIssue.AI_NOT_CONFIGURED)

    # Get issue to analyze
    issue = ctx.get("jira_issue") or ctx.get("selected_issue")
    if not issue:
        ctx.textual.error_text(msg.Steps.AIIssue.NO_ISSUE_FOUND)
        ctx.textual.end_step("error")
        return Error(msg.Steps.AIIssue.NO_ISSUE_FOUND)

    # Create JiraAgent instance and analyze issue with loading indicator
    with ctx.textual.loading(msg.Steps.AIIssue.ANALYZING):
        jira_agent = JiraAgent(ai_client, ctx.jira)
        analysis = jira_agent.analyze_issue(
            issue_key=issue.key,
            include_subtasks=True,
            include_comments=False,
            include_linked_issues=False
        )

    # Build formatted analysis for display
    # Use template from config if specified, otherwise use built-in formatter
    template_name = jira_agent.config.template if jira_agent.config.template else None
    formatter = IssueAnalysisMarkdownFormatter(template_path=template_name)
    ai_analysis = formatter.format(analysis)

    # Display analysis
    ctx.textual.text("")
    ctx.textual.bold_primary_text("AI Analysis Results")
    ctx.textual.text("")

    # Show issue header
    ctx.textual.bold_text(f"{issue.key}: {issue.summary}")
    ctx.textual.dim_text(f"Type: {issue.issue_type} | Status: {issue.status} | Priority: {issue.priority}")
    ctx.textual.text("")

    # Show AI analysis as markdown
    ctx.textual.markdown(ai_analysis)

    # Show token usage
    if analysis.total_tokens_used > 0:
        ctx.textual.dim_text(f"Tokens used: {analysis.total_tokens_used}")

    # Save structured analysis to context
    ctx.set("ai_analysis_structured", {
        "functional_requirements": analysis.functional_requirements,
        "non_functional_requirements": analysis.non_functional_requirements,
        "acceptance_criteria": analysis.acceptance_criteria,
        "technical_approach": analysis.technical_approach,
        "dependencies": analysis.dependencies,
        "risks": analysis.risks,
        "edge_cases": analysis.edge_cases,
        "suggested_subtasks": analysis.suggested_subtasks,
        "complexity_score": analysis.complexity_score,
        "estimated_effort": analysis.estimated_effort
    })

    ctx.textual.end_step("success")
    return Success(
        "AI analysis completed",
        metadata={
            "ai_analysis": ai_analysis,
            "analyzed_issue_key": issue.key,
            "tokens_used": analysis.total_tokens_used,
            "complexity": analysis.complexity_score,
            "effort": analysis.estimated_effort
        }
    )


__all__ = ["ai_analyze_issue_requirements_step"]
