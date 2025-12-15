"""
AI-powered JIRA issue analysis step
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from rich.markdown import Markdown
from ..messages import msg


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
    """
    if ctx.views:
        ctx.views.step_header("ai_analyze_issue", ctx.current_step, ctx.total_steps)

    # Check if AI is available
    if not ctx.ai or not ctx.ai.is_available():
        if ctx.ui:
            ctx.ui.panel.print(msg.Steps.AIIssue.AI_NOT_CONFIGURED_SKIP, panel_type="info")
        return Skip(msg.Steps.AIIssue.AI_NOT_CONFIGURED)

    # Get issue to analyze
    issue = ctx.get("jira_issue") or ctx.get("selected_issue")
    if not issue:
        if ctx.ui:
            ctx.ui.panel.print(msg.Steps.AIIssue.NO_ISSUE_FOUND, panel_type="error")
        return Error(msg.Steps.AIIssue.NO_ISSUE_FOUND)

    # Build context for AI
    issue_context = f"""# JIRA Issue Analysis Request

**Issue Key:** {issue.key}
**Type:** {issue.issue_type}
**Status:** {issue.status}
**Priority:** {issue.priority}
**Assignee:** {issue.assignee or "Unassigned"}

**Summary:**
{issue.summary}

**Description:**
{issue.description or "No description provided"}

**Labels:** {', '.join(issue.labels) if issue.labels else "None"}
**Components:** {', '.join(issue.components) if issue.components else "None"}
"""

    # Build AI prompt
    prompt = f"""{issue_context}

Please provide a comprehensive analysis of this JIRA issue with the following sections:

## 1. Issue Overview
Provide a brief summary of what this issue is asking for.

## 2. Requirements Breakdown
List the specific requirements and acceptance criteria (extract or infer from description).

## 3. Technical Considerations
Identify technical aspects, technologies, or systems involved.

## 4. Potential Challenges
List possible challenges, risks, or blockers.

## 5. Implementation Approach
Suggest a high-level implementation approach or steps.

## 6. Missing Information
Identify any critical information that's missing from the issue description.

## 7. Estimated Complexity
Rate the complexity (Low/Medium/High) and explain why.

Format your response in clear markdown with proper headers and bullet points.
"""

    if ctx.ui:
        ctx.ui.text.info(msg.Steps.AIIssue.ANALYZING)
        ctx.ui.spacer.small()

    # Generate AI analysis
    from titan_cli.ai.models import AIMessage

    messages = [AIMessage(role="user", content=prompt)]
    response = ctx.ai.generate(messages, max_tokens=2000, temperature=0.7)

    ai_analysis = response.content

    # Display analysis
    if ctx.ui:
        ctx.ui.spacer.small()
        ctx.ui.text.title("AI Analysis Results")
        ctx.ui.spacer.small()

        # Show issue header
        ctx.ui.text.subtitle(f"{issue.key}: {issue.summary}")
        ctx.ui.text.body(f"Type: {issue.issue_type} | Status: {issue.status} | Priority: {issue.priority}", style="dim")
        ctx.ui.spacer.small()

        # Show AI analysis as markdown
        ctx.ui.panel.print(Markdown(ai_analysis), title=None, panel_type="default")
        ctx.ui.spacer.small()

    return Success(
        "AI analysis completed",
        metadata={
            "ai_analysis": ai_analysis,
            "analyzed_issue_key": issue.key
        }
    )


__all__ = ["ai_analyze_issue_requirements_step"]
