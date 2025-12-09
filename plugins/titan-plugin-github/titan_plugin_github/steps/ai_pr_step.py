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
        prompt = f"""Analyze this branch and generate a professional pull request.

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

## Instructions
Generate a concise Pull Request that:
1. **Title**: Follow conventional commits (type(scope): description), max 72 chars
   - Examples: "feat(auth): add OAuth2 integration", "fix(api): resolve race condition in cache"
2. **Description**: CRITICAL - Maximum 500 characters. Be concise and focus on:
   - What changed (1-2 sentences)
   - Why it changed (1 sentence)
   - Key bullet points if needed (max 3)

Format your response EXACTLY like this:
TITLE: <conventional commit title>

DESCRIPTION:
<concise description - MAX 500 chars>"""

        # Show progress
        if ctx.ui:
            ctx.ui.text.info("🤖 Generating PR description with AI...")

        # Call AI (max_tokens reduced since we only need title + 500 char description)
        from titan_cli.ai.models import AIMessage

        messages = [AIMessage(role="user", content=prompt)]
        response = ctx.ai.generate(messages, max_tokens=800, temperature=0.7)

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

        # Truncate title if too long
        if len(title) > 72:
            title = title[:69] + "..."

        # Truncate description to 500 chars max
        if len(description) > 500:
            if ctx.ui:
                ctx.ui.text.warning(f"⚠️  AI generated {len(description)} chars, truncating to 500")
            description = description[:497] + "..."

        # Validate description has real content (not just whitespace)
        if not description or len(description.strip()) < 10:
            if ctx.ui:
                ctx.ui.text.warning(f"⚠️  AI generated an empty or very short description.")
                ctx.ui.text.body("Full AI response:")
                ctx.ui.text.body(ai_response[:1000])
            return Error("AI generated an empty or incomplete PR description")

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle("📝 AI Generated PR:")
            ctx.ui.spacer.small()

            # Show title
            ctx.ui.text.body("Title:", style="bold")
            ctx.ui.text.body(f"  {title}", style="cyan")

            # Warn if title is too long
            if len(title) > 72:
                ctx.ui.text.warning(f"  ⚠️  Title is {len(title)} chars (recommended: ≤72)")

            ctx.ui.spacer.small()

            # Show description (max 500 chars already enforced)
            ctx.ui.text.body("Description:", style="bold")

            # Print line by line for better formatting
            for line in description.split('\n'):
                ctx.ui.text.body(f"  {line}", style="dim")

            ctx.ui.spacer.small()

            # Single confirmation for both title and description
            use_ai_pr = ctx.views.prompts.ask_confirm(
                "Use this AI-generated PR?",
                default=True
            )

            if not use_ai_pr:
                ctx.ui.text.warning("AI suggestion rejected. Will prompt for manual input.")
                return Skip("User rejected AI-generated PR")

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
