# plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py
"""
AI-powered PR description generation step.

Uses PRAgent to analyze branch context and generate PR content.
"""

from rich.markdown import Markdown
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip

from ..agents import PRAgent
from ..messages import msg


def ai_suggest_pr_description(ctx: WorkflowContext) -> WorkflowResult:
    """
    Generate PR title and description using PRAgent.

    Uses PRAgent to analyze the complete branch context and generate:
    - PR title following conventional commits
    - PR description following template (if exists)
    - Appropriate detail level based on PR size

    Requires:
        ctx.ai: An initialized AIClient
        ctx.git: An initialized GitClient
        ctx.github: An initialized GitHubClient

    Inputs (from ctx.data):
        pr_head_branch (str): The head branch for the PR

    Outputs (saved to ctx.data):
        pr_title (str): AI-generated PR title
        pr_body (str): AI-generated PR description
        pr_size (str): Size classification (small/medium/large/very large)
        ai_generated (bool): True if AI generated the content

    Returns:
        Success: PR description generated
        Skip: AI not configured or user declined
        Error: Failed to generate PR description
    """
    # Show step header
    if ctx.views:
        ctx.views.step_header(
            name="AI Generate PR Description",
            step_type="plugin",
            step_detail="github.ai_suggest_pr_description"
        )

    # Check if AI is configured
    if not ctx.ai or not ctx.ai.is_available():
        if ctx.ui:
            ctx.ui.panel.print(
                msg.GitHub.AI.AI_NOT_CONFIGURED,
                panel_type="info"
            )
            ctx.ui.spacer.small()
        return Skip(msg.GitHub.AI.AI_NOT_CONFIGURED)

    # Get Git client
    if not ctx.git:
        return Error(msg.GitHub.AI.GIT_CLIENT_NOT_AVAILABLE)

    # Get branch info
    head_branch = ctx.get("pr_head_branch")
    if not head_branch:
        return Error(msg.GitHub.AI.MISSING_PR_HEAD_BRANCH)

    base_branch = ctx.git.main_branch

    try:
        # Show progress
        if ctx.ui:
            ctx.ui.text.info(msg.GitHub.AI.ANALYZING_BRANCH_DIFF.format(
                head_branch=head_branch,
                base_branch=base_branch
            ))

        # Create PRAgent instance
        pr_agent = PRAgent(
            ai_client=ctx.ai,
            git_client=ctx.git,
            github_client=ctx.github
        )

        # Use PRAgent to analyze and generate PR content
        if ctx.ui:
            ctx.ui.text.info(msg.GitHub.AI.GENERATING_PR_DESCRIPTION)

        analysis = pr_agent.analyze_and_plan(
            head_branch=head_branch,
            base_branch=base_branch,
            auto_stage=False  # Only analyze branch commits, not uncommitted changes
        )

        # Check if PR content was generated (need commits in branch)
        if not analysis.pr_title or not analysis.pr_body:
            if ctx.ui:
                ctx.ui.panel.print(
                    "No commits found in branch to generate PR description.",
                    panel_type="info"
                )
                ctx.ui.spacer.small()
            return Skip("No commits found for PR generation")

        # Show PR size info
        if ctx.ui and analysis.pr_size:
            ctx.ui.text.info(msg.GitHub.AI.PR_SIZE_INFO.format(
                pr_size=analysis.pr_size,
                files_changed=analysis.files_changed,
                diff_lines=analysis.lines_changed,
                max_chars="varies by size"
            ))

        # Show PR preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle(msg.GitHub.AI.AI_GENERATED_PR_TITLE)
            ctx.ui.spacer.small()

            # Show title
            ctx.ui.text.body(msg.GitHub.AI.TITLE_LABEL, style="bold")
            ctx.ui.text.body(f"  {analysis.pr_title}", style="cyan")

            # Warn if title is too long
            if len(analysis.pr_title) > 72:
                ctx.ui.text.warning(msg.GitHub.AI.TITLE_TOO_LONG_WARNING.format(
                    length=len(analysis.pr_title)
                ))

            ctx.ui.spacer.small()

            # Show description
            ctx.ui.text.body(msg.GitHub.AI.DESCRIPTION_LABEL, style="bold")
            ctx.ui.panel.print(
                Markdown(analysis.pr_body),
                title=None,
                panel_type="default"
            )

            ctx.ui.spacer.small()

            # Single confirmation for both title and description
            use_ai_pr = ctx.views.prompts.ask_confirm(
                msg.GitHub.AI.CONFIRM_USE_AI_PR,
                default=True
            )

            if not use_ai_pr:
                ctx.ui.text.warning(msg.GitHub.AI.AI_SUGGESTION_REJECTED)
                return Skip("User rejected AI-generated PR")

        # Show success panel
        if ctx.ui:
            ctx.ui.panel.print(
                "AI generated PR description successfully",
                panel_type="success"
            )
            ctx.ui.spacer.small()

        # Success - save to context
        metadata = {
            "ai_generated": True,
            "pr_title": analysis.pr_title,
            "pr_body": analysis.pr_body,
            "pr_size": analysis.pr_size
        }

        return Success(
            msg.GitHub.AI.AI_GENERATED_PR_DESCRIPTION_SUCCESS,
            metadata=metadata
        )

    except Exception as e:
        # Don't fail the workflow, just skip AI and use manual prompts
        if ctx.ui:
            ctx.ui.text.warning(msg.GitHub.AI.AI_GENERATION_FAILED.format(e=e))
            ctx.ui.text.info(msg.GitHub.AI.FALLBACK_TO_MANUAL)

        return Skip(msg.GitHub.AI.AI_GENERATION_FAILED.format(e=e))


# Export for plugin registration
__all__ = ["ai_suggest_pr_description"]
