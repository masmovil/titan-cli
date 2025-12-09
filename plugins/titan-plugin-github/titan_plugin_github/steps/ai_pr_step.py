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

        # Calculate PR size metrics for dynamic char limit
        diff_lines = len(branch_diff.split('\n'))

        # Estimate files changed (count file headers in diff)
        import re
        file_pattern = r'^diff --git'
        files_changed = len(re.findall(file_pattern, branch_diff, re.MULTILINE))

        # Dynamic character limit based on PR size
        if files_changed <= 3 and diff_lines < 100:
            # Small PR: bug fix, doc update, small feature
            max_chars = 500
            pr_size = "small"
        elif files_changed <= 10 and diff_lines < 500:
            # Medium PR: feature, moderate refactor
            max_chars = 1200
            pr_size = "medium"
        elif files_changed <= 30 and diff_lines < 2000:
            # Large PR: architectural changes, new modules
            max_chars = 2000
            pr_size = "large"
        else:
            # Very large PR: major refactor, breaking changes
            max_chars = 3000
            pr_size = "very large"

        if ctx.ui:
            ctx.ui.text.info(f"📏 PR Size: {pr_size} ({files_changed} files, {diff_lines} lines) → Max description: {max_chars} chars")

        # Read PR template (REQUIRED - must follow template if exists)
        template_path = Path(".github/pull_request_template.md")
        template = ""
        has_template = template_path.exists()

        if has_template:
            try:
                with open(template_path, "r") as f:
                    template = f.read()
            except Exception as e:
                if ctx.ui:
                    ctx.ui.text.warning(f"Failed to read PR template: {e}")
                has_template = False

        # Build prompt - MUST follow template if available
        if has_template and template:
            prompt = f"""Analyze this branch and generate a professional pull request following the EXACT template structure.

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

## PR Template (MUST FOLLOW THIS STRUCTURE)
```markdown
{template}
```

## CRITICAL Instructions
1. **Title**: Follow conventional commits (type(scope): description), max 72 chars
   - Examples: "feat(auth): add OAuth2 integration", "fix(api): resolve race condition in cache"

2. **Description**: MUST follow the template structure above but keep it under {max_chars} characters total
   - Fill in the template sections (Summary, Type of Change, Changes Made, etc.)
   - Mark checkboxes appropriately with [x]
   - Adjust detail level based on PR size ({pr_size}):
     * Small PRs: Brief, 1-2 lines per section
     * Medium PRs: Moderate detail, 2-3 lines per section
     * Large PRs: Comprehensive, 3-5 lines per section with examples
     * Very Large PRs: Detailed architecture explanations, migration guides
   - Total description length MUST be ≤{max_chars} chars

Format your response EXACTLY like this:
TITLE: <conventional commit title>

DESCRIPTION:
<template-based description - MAX {max_chars} chars total>"""
        else:
            # Fallback when no template exists
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

## Instructions (No template available - use standard format)
Generate a Pull Request appropriate for a {pr_size} PR:
1. **Title**: Follow conventional commits (type(scope): description), max 72 chars
   - Examples: "feat(auth): add OAuth2 integration", "fix(api): resolve race condition in cache"
2. **Description**: CRITICAL - Maximum {max_chars} characters. Detail level based on PR size:
   - Small ({pr_size}): Brief summary (1-2 sentences) + key changes (2-3 bullets)
   - Medium: What changed (2-3 sentences) + why (1-2 sentences) + key changes (4-5 bullets)
   - Large: Comprehensive overview + architecture changes + migration notes + testing strategy
   - Very Large: Full context + breaking changes + upgrade guide + examples

Format your response EXACTLY like this:
TITLE: <conventional commit title>

DESCRIPTION:
<description matching PR size - MAX {max_chars} chars>"""

        # Show progress
        if ctx.ui:
            ctx.ui.text.info("🤖 Generating PR description with AI...")

        # Calculate max_tokens based on PR size (chars to tokens ratio ~0.75)
        # Add buffer for formatting
        estimated_tokens = int(max_chars * 0.75) + 200  # +200 for TITLE/DESCRIPTION labels and formatting
        max_tokens = min(estimated_tokens, 4000)  # Cap at 4000 tokens

        # Call AI with dynamic token limit
        from titan_cli.ai.models import AIMessage

        messages = [AIMessage(role="user", content=prompt)]
        response = ctx.ai.generate(messages, max_tokens=max_tokens, temperature=0.7)

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

        # Truncate description to max_chars if needed
        if len(description) > max_chars:
            if ctx.ui:
                ctx.ui.text.warning(f"⚠️  AI generated {len(description)} chars, truncating to {max_chars}")
            description = description[:max_chars - 3] + "..."

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
