# plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py
"""
AI-powered PR description generation step.

Uses AIClient to analyze git changes and suggest PR title and body.
"""

from pathlib import Path
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip


def ai_suggest_pr_description(ctx: WorkflowContext) -> WorkflowResult:
    """
    Generate PR title and description using AI analysis.

    Analyzes the full branch diff (all commits) and uses AI to suggest
    a professional PR title and description following the PR template.

    Requires:
        ctx.github: An initialized GitHubClient.
        ctx.git: An initialized GitClient.
        ctx.ai: An initialized AIClient.

    Inputs (from ctx.data):
        pr_head_branch (str): The head branch for the PR.

    Outputs (saved to ctx.data):
        pr_title (str): AI-generated PR title.
        pr_body (str): AI-generated PR description.

    Returns:
        Success: PR title and body generated
        Skip: AI not configured or user declined
        Error: Failed to generate PR description
    """
    # Check if AI is configured
    if not ctx.ai or not ctx.ai.is_available():
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # Get GitHub and Git clients
    if not ctx.github:
        return Error("GitHub client is not available in the workflow context.")
    if not ctx.git:
        return Error("Git client is not available in the workflow context.")

    # Get branch info
    head_branch = ctx.get("pr_head_branch")
    if not head_branch:
        return Error("Missing pr_head_branch in context")

    base_branch = ctx.git.main_branch

    try:
        # Get full branch diff (this is the key for AI analysis)
        if ctx.ui:
            ctx.ui.text.info(f"📊 Analyzing branch diff: {head_branch} vs {base_branch}...")

        # Get commits in the branch
        try:
            commits = ctx.git.get_branch_commits(base_branch, head_branch)
            branch_diff = ctx.git.get_branch_diff(base_branch, head_branch)
        except Exception as e:
            return Error(f"Failed to get branch diff: {e}")

        if not branch_diff or not commits:
            return Skip("No changes found between branches")

        # Build context for AI
        commits_text = "\n".join([f"  - {c}" for c in commits[:15]])
        if len(commits) > 15:
            commits_text += f"\n  ... and {len(commits) - 15} more commits"

        # Limit diff size to avoid token overflow
        diff_preview = branch_diff[:8000] if branch_diff else "No diff available"
        if len(branch_diff) > 8000:
            diff_preview += "\n\n... (diff truncated for brevity)"

        # Read PR template
        template_path = Path(".github/pull_request_template.md")
        template = ""
        if template_path.exists():
            with open(template_path, "r") as f:
                template = f.read()

        # Build comprehensive prompt with template
        prompt = f"""Analyze this branch and generate a professional pull request following the template.

## Branch Information
- Head branch: {head_branch}
- Base branch: {base_branch}
- Total commits: {len(commits)}

## Commits in Branch
{commits_text}

## Branch Diff Preview
```diff
{diff_preview}
```

## PR Template to Follow
{template if template else "No template found - use standard format"}

## Instructions
Generate a complete Pull Request that:
1. **Title**: Follow conventional commits (type(scope): description), max 72 chars
   - Examples: "feat(auth): add OAuth2 integration", "fix(api): resolve race condition in cache"
2. **Body**: Follow the PR template exactly, filling in all sections:
   - Summary: What changed and why (2-3 sentences)
   - Type of Change: Mark appropriate checkboxes with [x]
   - Changes Made: Bullet list of key changes
   - Testing: How this was tested
   - Checklist: Mark completed items with [x]

Format your response EXACTLY like this:
TITLE: <conventional commit title>

DESCRIPTION:
<full PR body following the template>"""

        # Show progress
        if ctx.ui:
            ctx.ui.text.info("🤖 Generating PR description with AI...")

        # Call AI
        from titan_cli.ai.models import AIMessage

        messages = [AIMessage(role="user", content=prompt)]
        response = ctx.ai.generate(messages, max_tokens=2048, temperature=0.7)

        ai_response = response.content

        if "TITLE:" not in ai_response or "DESCRIPTION:" not in ai_response:
            return Error(
                f"AI response format incorrect. Expected 'TITLE:' and 'DESCRIPTION:' sections.\n"
                f"Got: {ai_response[:200]}..."
            )

        # Extract title and description
        parts = ai_response.split("DESCRIPTION:", 1)
        title = parts[0].replace("TITLE:", "").strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        # Clean up title (remove quotes if present)
        title = title.strip('"').strip("'")

        # Debug: Check if description is empty
        if not description or description == "":
            if ctx.ui:
                ctx.ui.text.warning(f"⚠️  AI generated an empty description. Full response was:")
                ctx.ui.text.body(ai_response[:500])
            return Error("AI generated an empty PR description")

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()

            # Show and confirm title
            ctx.ui.text.subtitle("📝 AI Generated PR Title:")
            ctx.ui.text.body(f"  {title}", style="bold cyan")

            # Warn if title is too long
            if len(title) > 72:
                ctx.ui.text.warning(f"  ⚠️  Title is {len(title)} chars (recommended: ≤72)")

            ctx.ui.spacer.small()

            use_title = ctx.views.prompts.ask_confirm(
                "Use this title?",
                default=True
            )

            if not use_title:
                ctx.ui.text.warning("AI title rejected. Will prompt for manual input.")
                return Skip("User rejected AI-generated title")

            # Show and confirm description
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle("📝 AI Generated PR Description:")
            ctx.ui.panel.render(description, title="Description", border_style="cyan")
            ctx.ui.spacer.small()

            use_description = ctx.views.prompts.ask_confirm(
                "Use this description?",
                default=True
            )

            if not use_description:
                ctx.ui.text.warning("AI description rejected. Will prompt for manual input.")
                return Skip("User rejected AI-generated description")

        # Success - save to context
        return Success(
            "AI generated PR description",
            metadata={
                "pr_title": title,
                "pr_body": description,
                "ai_generated": True
            }
        )

    except Exception as e:
        # Don't fail the workflow, just skip AI and use manual prompts
        if ctx.ui:
            ctx.ui.text.warning(f"AI generation failed: {e}")
            ctx.ui.text.info("Falling back to manual PR creation...")

        return Skip(f"AI generation failed: {e}")


# Export for plugin registration
__all__ = ["ai_suggest_pr_description"]
