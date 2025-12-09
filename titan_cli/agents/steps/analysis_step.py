"""
AI Agent Analysis Workflow Steps

Steps that use AI agents to analyze data populated by previous workflow steps.
Agents run in "analysis mode" - they receive pre-computed data and don't execute tools.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from typing import Optional


def ai_analyze_changes_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    AI Agent analyzes git changes and provides insights.

    This step runs an AI agent in ANALYSIS MODE (no tool execution).
    It reads data from ctx.data (populated by previous steps like get_git_status_step)
    and uses AI to analyze it.

    Requires in ctx.data:
        - git_status (from get_git_status_step) OR
        - git_diff (from a hypothetical get_git_diff_step)

    Optional in ctx.data:
        - analysis_prompt: Custom prompt for the agent

    Sets in ctx.data:
        - ai_analysis: The agent's analysis text
        - ai_suggestions: Structured suggestions (if any)

    Returns:
        Success: With analysis in metadata
        Error: If AI is not configured or analysis fails
        Skip: If no data to analyze

    Example workflow:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,      # Populates ctx.data["git_status"]
            ai_analyze_changes_step   # Analyzes git_status with AI
        ])
    """

    # Check if AI is configured
    if not ctx.ai:
        return Skip("AI not configured, skipping analysis")

    # Check if there's data to analyze
    git_status = ctx.data.get("git_status")
    git_diff = ctx.data.get("git_diff")

    if not git_status and not git_diff:
        return Skip("No git data found in context to analyze")

    # Skip if working directory is clean
    if git_status and git_status.is_clean:
        return Skip("Working directory is clean, nothing to analyze")

    try:
        # Build analysis prompt from context data
        prompt = _build_analysis_prompt(ctx)

        # Get custom system prompt or use default
        system_prompt = ctx.data.get("analysis_system_prompt", _get_default_system_prompt())

        # Call AI (no tools - pure text analysis)
        response = ctx.ai.generate(
            prompt=prompt,
            system_prompt=system_prompt
        )

        return Success(
            message="AI analysis completed",
            metadata={
                "ai_analysis": response,
                "analysis_mode": "changes_analysis"
            }
        )

    except Exception as e:
        return Error(f"AI analysis failed: {e}", exception=e)


def ai_suggest_commit_message_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    AI Agent suggests a conventional commit message based on changes.

    This is a specialized analysis step that focuses on generating
    commit messages following conventional commits format.

    Requires in ctx.data:
        - git_status OR git_diff

    Optional in ctx.data:
        - commit_type_hint: Suggest commit type (feat, fix, etc.)

    Sets in ctx.data:
        - suggested_commit_message: AI-generated commit message
        - commit_message: Sets the suggested message as commit_message
                         (can be used by create_git_commit_step)

    Returns:
        Success: With suggested commit message
        Error: If AI fails
        Skip: If no changes or AI not available

    Example workflow:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,             # Get status
            ai_suggest_commit_message_step,  # AI suggests message
            create_git_commit_step           # Uses suggested message
        ])
    """

    # Check AI availability
    if not ctx.ai:
        return Skip("AI not configured, skipping commit message suggestion")

    # Check for data
    git_status = ctx.data.get("git_status")
    if git_status and git_status.is_clean:
        return Skip("Working directory is clean, no commit needed")

    if not git_status and not ctx.data.get("git_diff"):
        return Skip("No git data to analyze for commit message")

    try:
        # Build commit-specific prompt
        prompt = _build_commit_message_prompt(ctx)
        system_prompt = _get_commit_message_system_prompt()

        # Call AI
        suggested_message = ctx.ai.generate(
            prompt=prompt,
            system_prompt=system_prompt
        )

        # Clean up the message (remove markdown, extra whitespace)
        suggested_message = suggested_message.strip().strip('`').strip()

        return Success(
            message=f"Suggested commit: {suggested_message}",
            metadata={
                "suggested_commit_message": suggested_message,
                "commit_message": suggested_message  # Auto-populate for next step
            }
        )

    except Exception as e:
        return Error(f"Failed to generate commit message: {e}", exception=e)


# ============================================================================
# Helper functions
# ============================================================================

def _build_analysis_prompt(ctx: WorkflowContext) -> str:
    """Build analysis prompt from context data."""

    parts = []

    # Custom prompt from context (if provided)
    if ctx.data.get("analysis_prompt"):
        parts.append(ctx.data["analysis_prompt"])
        parts.append("\n\n")
    else:
        parts.append("Analyze the following git repository changes:\n\n")

    # Git status
    git_status = ctx.data.get("git_status")
    if git_status:
        parts.append("## Repository Status\n\n")
        parts.append(f"- Branch: {git_status.branch}\n")
        parts.append(f"- Clean: {git_status.is_clean}\n")

        if not git_status.is_clean:
            if git_status.modified_files:
                parts.append(f"- Modified files: {len(git_status.modified_files)}\n")
                for file in git_status.modified_files[:10]:  # Limit to 10
                    parts.append(f"  - {file}\n")

            if git_status.untracked_files:
                parts.append(f"- Untracked files: {len(git_status.untracked_files)}\n")

        parts.append("\n")

    # Git diff (if available)
    git_diff = ctx.data.get("git_diff")
    if git_diff:
        parts.append("## Changes\n\n")
        parts.append(f"```diff\n{git_diff[:2000]}\n```\n\n")  # Limit diff size

    # PR info (if available)
    if ctx.data.get("pr_number"):
        parts.append("## Pull Request Info\n\n")
        parts.append(f"- Number: #{ctx.data['pr_number']}\n")
        if ctx.data.get("pr_title"):
            parts.append(f"- Title: {ctx.data['pr_title']}\n")
        parts.append("\n")

    return "".join(parts)


def _build_commit_message_prompt(ctx: WorkflowContext) -> str:
    """Build commit message generation prompt."""

    parts = []

    # Instruction
    parts.append("Generate a conventional commit message for these changes.\n\n")

    # Hint about commit type (if provided)
    if ctx.data.get("commit_type_hint"):
        parts.append(f"Expected type: {ctx.data['commit_type_hint']}\n\n")

    # Git status
    git_status = ctx.data.get("git_status")
    if git_status and not git_status.is_clean:
        parts.append("Modified files:\n")
        for file in git_status.modified_files[:20]:
            parts.append(f"- {file}\n")
        parts.append("\n")

    # Git diff (if available)
    git_diff = ctx.data.get("git_diff")
    if git_diff:
        # Limit diff to avoid token overflow
        parts.append("Changes:\n")
        parts.append(f"```diff\n{git_diff[:1500]}\n```\n")

    return "".join(parts)


def _get_default_system_prompt() -> str:
    """Default system prompt for general analysis."""
    return """You are a Platform Engineering expert analyzing Git repository changes.

Provide concise, actionable insights about:
- What changed and why
- Potential issues or concerns
- Recommendations for improvements

Be direct and technical."""


def _get_commit_message_system_prompt() -> str:
    """System prompt for commit message generation."""
    return """You are a Git commit message expert.

Generate commit messages following conventional commits format:
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore, ci, build, perf

Rules:
1. Use lowercase for type and description
2. Keep description under 72 characters
3. Be specific but concise
4. Focus on WHAT changed, not HOW
5. Return ONLY the commit message, no explanations

Example: feat(auth): add OAuth2 login support"""
