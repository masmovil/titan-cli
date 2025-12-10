# plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py
"""
AI-powered PR description generation step.

Uses AIClient to analyze git changes and suggest PR title and body.
"""

from pathlib import Path
from rich.markdown import Markdown
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from ..utils import get_pr_size_estimation
from ..messages import msg

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

    # Get GitHub and Git clients
    if not ctx.github:
        return Error(msg.GitHub.AI.GITHUB_CLIENT_NOT_AVAILABLE)
    if not ctx.git:
        return Error(msg.GitHub.AI.GIT_CLIENT_NOT_AVAILABLE)

    # Get branch info
    head_branch = ctx.get("pr_head_branch")
    if not head_branch:
        return Error(msg.GitHub.AI.MISSING_PR_HEAD_BRANCH)

    base_branch = ctx.git.main_branch

    try:
        # Get full branch diff (this is the key for AI analysis)
        if ctx.ui:
            ctx.ui.text.info(msg.GitHub.AI.ANALYZING_BRANCH_DIFF.format(head_branch=head_branch, base_branch=base_branch))

        # Get commits in the branch
        try:
            commits = ctx.git.get_branch_commits(base_branch, head_branch)
            branch_diff = ctx.git.get_branch_diff(base_branch, head_branch)
        except Exception as e:
            return Error(msg.GitHub.AI.FAILED_TO_GET_BRANCH_DIFF.format(e=e))

        if not branch_diff or not commits:
            return Skip(msg.GitHub.AI.NO_CHANGES_FOUND)

        # Build context for AI
        commits_text = "\n".join([f"  - {c}" for c in commits[:15]])
        if len(commits) > 15:
            commits_text += msg.GitHub.AI.COMMITS_TRUNCATED.format(count=len(commits) - 15)

        # Limit diff size to avoid token overflow
        diff_preview = branch_diff[:8000] if branch_diff else msg.GitHub.AI.NO_DIFF_AVAILABLE
        if len(branch_diff) > 8000:
            diff_preview += msg.GitHub.AI.DIFF_TRUNCATED

        # Calculate PR size metrics for dynamic char limit
        size_estimation = get_pr_size_estimation(branch_diff)
        pr_size = size_estimation.pr_size
        max_chars = size_estimation.max_chars

        if ctx.ui:
            ctx.ui.text.info(msg.GitHub.AI.PR_SIZE_INFO.format(
                pr_size=pr_size,
                files_changed=size_estimation.files_changed,
                diff_lines=size_estimation.diff_lines,
                max_chars=max_chars
            ))

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
                    ctx.ui.text.warning(msg.GitHub.AI.FAILED_TO_READ_PR_TEMPLATE.format(e=e))
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
            ctx.ui.text.info(msg.GitHub.AI.GENERATING_PR_DESCRIPTION)

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
                msg.GitHub.AI.AI_RESPONSE_FORMAT_INCORRECT.format(response_preview=ai_response[:200])
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
                ctx.ui.text.warning(msg.GitHub.AI.AI_GENERATED_TRUNCATING.format(actual_len=len(description), max_chars=max_chars))
            description = description[:max_chars - 3] + "..."

        # Validate description has real content (not just whitespace)
        if not description or len(description.strip()) < 10:
            if ctx.ui:
                ctx.ui.text.warning(msg.GitHub.AI.AI_GENERATED_EMPTY_SHORT)
                ctx.ui.text.body(msg.GitHub.AI.FULL_AI_RESPONSE)
                ctx.ui.text.body(ai_response[:1000])
            return Error(msg.GitHub.AI.AI_GENERATED_INCOMPLETE)

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle(msg.GitHub.AI.AI_GENERATED_PR_TITLE)
            ctx.ui.spacer.small()

            # Show title
            ctx.ui.text.body(msg.GitHub.AI.TITLE_LABEL, style="bold")
            ctx.ui.text.body(f"  {title}", style="cyan")

            # Warn if title is too long
            if len(title) > 72:
                ctx.ui.text.warning(msg.GitHub.AI.TITLE_TOO_LONG_WARNING.format(length=len(title)))

            ctx.ui.spacer.small()

            # Show description
            ctx.ui.text.body(msg.GitHub.AI.DESCRIPTION_LABEL, style="bold")
            ctx.ui.panel.print(Markdown(description), title=None, panel_type="default")


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
                "AI PR description generated successfully",
                panel_type="success"
            )
            ctx.ui.spacer.small()

        # Success - save to context
        return Success(
            msg.GitHub.AI.AI_GENERATED_PR_DESCRIPTION_SUCCESS,
            metadata={
                "pr_title": title,
                "pr_body": description,
                "ai_generated": True
            }
        )

    except Exception as e:
        # Don't fail the workflow, just skip AI and use manual prompts
        if ctx.ui:
            ctx.ui.text.warning(msg.GitHub.AI.AI_GENERATION_FAILED.format(e=e))
            ctx.ui.text.info(msg.GitHub.AI.FALLBACK_TO_MANUAL)

        return Skip(msg.GitHub.AI.AI_GENERATION_FAILED.format(e=e))


# Export for plugin registration
__all__ = ["ai_suggest_pr_description"]
