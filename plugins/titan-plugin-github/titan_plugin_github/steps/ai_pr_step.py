"""
AI-powered PR description generation step.

Uses PlatformAgent to analyze git changes and suggest PR title and body.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_cli.agents import PlatformAgent


def ai_suggest_pr_description(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    """
    Generate PR title and body using AI analysis.

    This step analyzes the current branch changes and uses AI to suggest
    a professional PR title and description.

    Reads from ctx.data:
        - use_ai: Whether to use AI (default: false, opt-in)
        - git_status: Current git status
        - current_branch: Current branch name
        - base_branch: Base branch for comparison

    Writes to ctx.data:
        - pr_title: AI-generated PR title
        - pr_body: AI-generated PR description

    Returns:
        Success: PR title and body generated
        Skip: AI not requested, not configured, or no changes found
        Error: Failed to generate PR description

    Example:
        In workflow YAML:
        ```yaml
        params:
          use_ai: true  # Explicitly opt-in to AI

        steps:
          - id: ai_suggest_pr
            name: "AI Suggest PR Description"
            plugin: github
            step: ai_suggest_pr_description
            optional: true
        ```
    """
    # Check if user explicitly opted-in to AI (default is false)
    use_ai = ctx.data.get("use_ai", False)
    if not use_ai:
        return Skip("AI not requested (use_ai=false). Using manual prompts for deterministic behavior.")

    # Check if AI is configured
    if not ctx.ai:
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # Get git status
    git_status = ctx.data.get("git_status")
    if not git_status or git_status.is_clean:
        return Skip("No changes to analyze for PR")

    # Get branch info
    current_branch = ctx.data.get("current_branch", "unknown")
    base_branch = ctx.data.get("base_branch", "main")

    try:
        # Get git client for branch diff analysis
        git_client = ctx.git
        if not git_client:
            return Error("Git client not available")

        # Get full branch diff (this is the key for AI analysis)
        if ctx.ui:
            ctx.ui.text.info(f"📊 Analyzing branch diff: {current_branch} vs {base_branch}...")

        try:
            # Get commits in the branch
            commits_result = git_client.get_branch_commits(base_branch, current_branch)
            commits = commits_result if commits_result else ctx.data.get("branch_commits", [])

            # Get full diff of the branch
            branch_diff = git_client.get_branch_diff(base_branch, current_branch)

        except Exception as e:
            if ctx.ui:
                ctx.ui.text.warning(f"Could not get branch diff: {e}")
            # Fallback to individual file diffs
            commits = []
            branch_diff = ""
            files_changed = git_status.modified_files + git_status.untracked_files
            for file_path in files_changed[:10]:  # Limit to avoid token overflow
                try:
                    diff = git_client.get_file_diff(file_path)
                    branch_diff += f"\n### {file_path}\n{diff}\n"
                except:
                    pass

        # Build context for AI
        files_changed = git_status.modified_files + git_status.untracked_files
        files_text = "\n".join(f"  - {f}" for f in files_changed[:30])

        if len(files_changed) > 30:
            files_text += f"\n  ... and {len(files_changed) - 30} more files"

        commits_text = ""
        if commits:
            commits_text = "\n".join(f"  - {c}" for c in commits[:15])
            if len(commits) > 15:
                commits_text += f"\n  ... and {len(commits) - 15} more commits"

        # Limit diff size to avoid token overflow
        diff_preview = branch_diff[:8000] if branch_diff else "No diff available"
        if len(branch_diff) > 8000:
            diff_preview += "\n\n... (diff truncated for brevity)"

        # Load PlatformAgent for PR generation
        agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")

        # Read PR template
        from pathlib import Path
        template_path = Path(".github/pull_request_template.md")
        template = ""
        if template_path.exists():
            with open(template_path, "r") as f:
                template = f.read()

        # Build comprehensive prompt with template
        user_context = f"""Analyze this branch and generate a professional pull request following the template.

## Branch Information
- Current branch: {current_branch}
- Base branch: {base_branch}
- Files changed: {len(files_changed)}
- Total commits: {len(commits) if commits else 'unknown'}

## Commits in Branch
{commits_text if commits_text else "No commit information available"}

## Changed Files
{files_text}

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
<full PR body following the template>
"""

        # Show progress
        if ctx.ui:
            ctx.ui.text.info("🤖 Generating PR description with AI...")

        # Run agent in analysis mode
        result = agent.run(
            ctx=ctx,
            user_context=user_context,
            mode="analysis"
        )

        if not isinstance(result, Success):
            return result

        # Parse AI response
        response = result.message

        if "TITLE:" not in response or "DESCRIPTION:" not in response:
            return Error(
                f"AI response format incorrect. Expected 'TITLE:' and 'DESCRIPTION:' sections.\n"
                f"Got: {response[:200]}..."
            )

        # Extract title and description
        parts = response.split("DESCRIPTION:", 1)
        title = parts[0].replace("TITLE:", "").strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        # Clean up title (remove quotes if present)
        title = title.strip('"').strip("'")

        # Validate title length
        if len(title) > 72:
            title = title[:69] + "..."

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle("📝 AI Generated PR:")
            ctx.ui.text.body(f"  Title: {title}", style="bold cyan")
            ctx.ui.spacer.small()
            ctx.ui.panel.render(description, title="Description", border_style="cyan")
            ctx.ui.spacer.small()

            # Ask user if they want to use it or modify
            use_ai = ctx.views.prompts.ask_confirm(
                "Use this AI-generated PR description?",
                default=True
            )

            if not use_ai:
                ctx.ui.text.warning("AI suggestion skipped. Will prompt for manual input.")
                return Skip("User chose to skip AI suggestion")

        # Success - save to context
        return Success(
            "AI generated PR description",
            metadata={
                "pr_title": title,
                "pr_body": description,
                "ai_generated": True
            }
        )

    except FileNotFoundError:
        return Skip(
            "PlatformAgent config not found at config/agents/platform_agent.toml. "
            "Falling back to manual PR creation."
        )
    except Exception as e:
        # Don't fail the workflow, just skip AI and use manual prompts
        if ctx.ui:
            ctx.ui.text.warning(f"AI generation failed: {e}")
            ctx.ui.text.info("Falling back to manual PR creation...")

        return Skip(f"AI generation failed: {e}")


# Export for plugin registration
__all__ = ["ai_suggest_pr_description"]
