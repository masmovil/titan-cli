# plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py
"""
AI-powered PR description generation step using PlatformAgent.

Uses PlatformAgent to analyze branch context and generate PR content.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_cli.ai.agents import PlatformAgent


def ai_suggest_pr_description(ctx: WorkflowContext) -> WorkflowResult:
    """
    Generate PR title and description using PlatformAgent.

    Uses PlatformAgent to:
    1. Analyze the complete branch context
    2. Determine if commits are needed
    3. Generate commit messages if needed
    4. Generate PR title and description following templates

    Requires:
        ctx.ai: An initialized AIClient
        ctx.git: An initialized GitClient
        ctx.github: An initialized GitHubClient (optional)

    Inputs (from ctx.data):
        pr_head_branch (str): The head branch for the PR

    Outputs (saved to ctx.data):
        pr_title (str): AI-generated PR title
        pr_body (str): AI-generated PR description
        commit_message (str): Optional commit message if changes need committing
        needs_commit (bool): Whether changes need to be committed
        pr_size (str): Size classification (small/medium/large/very large)
        tokens_used (int): Total tokens consumed

    Returns:
        Success: PR description generated
        Skip: AI not configured or user declined
        Error: Failed to generate PR description
    """
    # Check AI availability
    if not ctx.ai or not ctx.ai.is_available():
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # Check Git client
    if not ctx.git:
        return Error("Git client is not available in the workflow context.")

    # Get branch info
    head_branch = ctx.get("pr_head_branch")
    if not head_branch:
        return Error("Missing pr_head_branch in context")

    base_branch = ctx.git.main_branch

    try:
        # Show progress
        if ctx.ui:
            ctx.ui.text.info(f"🤖 Analyzing branch with PlatformAgent...")
            ctx.ui.text.info(f"   Branch: {head_branch} → {base_branch}")

        # Create PlatformAgent
        platform_agent = PlatformAgent(
            ai_client=ctx.ai,
            git_client=ctx.git,
            github_client=ctx.github
        )

        # Analyze and plan
        analysis = platform_agent.analyze_and_plan(
            head_branch=head_branch,
            base_branch=base_branch,
            auto_stage=False  # Only analyze staged changes
        )

        # Check if we have PR content
        if not analysis.pr_title:
            return Skip("No changes found between branches")

        # Show results
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle("📊 Platform Agent Analysis:")
            ctx.ui.spacer.small()

            # PR Info
            ctx.ui.text.body(f"PR Size: {analysis.pr_size}", style="bold")
            ctx.ui.text.body(f"Files: {analysis.files_changed}, Lines: {analysis.lines_changed}", style="dim")
            ctx.ui.text.body(f"Tokens used: {analysis.total_tokens_used}", style="dim")

            ctx.ui.spacer.small()

            # PR Title
            ctx.ui.text.body("PR Title:", style="bold")
            ctx.ui.text.body(f"  {analysis.pr_title}", style="cyan")

            # Warn if title is too long
            if len(analysis.pr_title) > 72:
                ctx.ui.text.warning(f"  ⚠️  Title is {len(analysis.pr_title)} chars (recommended: ≤72)")

            ctx.ui.spacer.small()

            # PR Description (preview - first 10 lines)
            ctx.ui.text.body("PR Description:", style="bold")
            preview_lines = analysis.pr_body.split('\n')[:10]
            for line in preview_lines:
                ctx.ui.text.body(f"  {line}", style="dim")

            if len(analysis.pr_body.split('\n')) > 10:
                ctx.ui.text.body("  ... (truncated)", style="dim")

            ctx.ui.spacer.small()

            # Commit info (if applicable)
            if analysis.needs_commit and analysis.commit_message:
                ctx.ui.text.body("Suggested Commit:", style="bold")
                ctx.ui.text.body(f"  {analysis.commit_message}", style="yellow")
                ctx.ui.spacer.small()

            # Ask for confirmation
            use_analysis = ctx.views.prompts.ask_confirm(
                "Use this AI-generated PR?",
                default=True
            )

            if not use_analysis:
                ctx.ui.text.warning("Platform Agent analysis rejected. Will prompt for manual input.")
                return Skip("User rejected Platform Agent analysis")

        # Success - save to context
        metadata = {
            "pr_title": analysis.pr_title,
            "pr_body": analysis.pr_body,
            "pr_size": analysis.pr_size,
            "tokens_used": analysis.total_tokens_used,
            "files_changed": analysis.files_changed,
            "lines_changed": analysis.lines_changed,
            "ai_generated": True
        }

        # Add commit info if available
        if analysis.needs_commit and analysis.commit_message:
            metadata["needs_commit"] = True
            metadata["commit_message"] = analysis.commit_message

        return Success(
            "Platform Agent generated PR description",
            metadata=metadata
        )

    except Exception as e:
        # Don't fail the workflow, just skip AI and use manual prompts
        if ctx.ui:
            ctx.ui.text.warning(f"Platform Agent failed: {e}")
            ctx.ui.text.info("Falling back to manual PR creation...")

        return Skip(f"Platform Agent failed: {e}")


# Export for plugin registration
__all__ = ["ai_suggest_pr_description"]
