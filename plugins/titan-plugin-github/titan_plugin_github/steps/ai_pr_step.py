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
        ctx.views.step_header("ai_pr_description", ctx.current_step, ctx.total_steps)

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
            auto_stage=True  # Enable auto-staging to detect uncommitted changes
        )

        # Check if anything was generated
        if not analysis.commit_message and (not analysis.pr_title or not analysis.pr_body):
            return Skip(msg.GitHub.AI.NO_CHANGES_FOUND)

        # Show PR size info
        if ctx.ui and analysis.pr_size:
            ctx.ui.text.info(msg.GitHub.AI.PR_SIZE_INFO.format(
                pr_size=analysis.pr_size,
                files_changed=analysis.files_changed,
                diff_lines=analysis.lines_changed,
                max_chars="varies by size"
            ))

        # FIRST: Show and confirm commit message if there are uncommitted changes
        # This happens BEFORE showing PR title/body so user sees commit message first
        if analysis.commit_message:
            if ctx.ui:
                ctx.ui.spacer.small()
                ctx.ui.text.subtitle(msg.GitHub.AI.AI_GENERATED_COMMIT_MESSAGE)
                ctx.ui.spacer.small()

                # Show commit message
                ctx.ui.text.body(msg.GitHub.AI.COMMIT_MESSAGE_LABEL, style="bold")
                ctx.ui.panel.print(
                    analysis.commit_message,
                    title=None,
                    panel_type="default"
                )

                ctx.ui.spacer.small()

                # Ask for confirmation
                use_ai_commit = ctx.views.prompts.ask_confirm(
                    msg.GitHub.AI.CONFIRM_USE_AI_COMMIT,
                    default=True
                )

                if not use_ai_commit:
                    ctx.ui.text.warning(msg.GitHub.AI.AI_COMMIT_REJECTED)
                    # User rejected commit message - skip entire AI analysis
                    return Skip("User rejected AI-generated commit message")

        # Show PR preview to user (only if PR content was generated)
        if analysis.pr_title and analysis.pr_body:
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
            success_msg = []
            if analysis.commit_message:
                success_msg.append("Commit message")
            if analysis.pr_title and analysis.pr_body:
                success_msg.append("PR description")

            if success_msg:
                ctx.ui.panel.print(
                    f"AI generated {' and '.join(success_msg)} successfully",
                    panel_type="success"
                )
                ctx.ui.spacer.small()

        # Success - save to context
        metadata = {
            "ai_generated": True
        }

        # Include PR content if generated
        if analysis.pr_title:
            metadata["pr_title"] = analysis.pr_title
        if analysis.pr_body:
            metadata["pr_body"] = analysis.pr_body
        if analysis.pr_size:
            metadata["pr_size"] = analysis.pr_size

        # Include commit message if generated
        if analysis.commit_message:
            metadata["commit_message"] = analysis.commit_message

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
