# plugins/titan-plugin-github/titan_plugin_github/agents/pr_agent.py
"""
PRAgent - Intelligent orchestrator for git workflows.

This agent analyzes the complete context of a branch and automatically:
1. Determines if changes need to be committed
2. Generates appropriate commit messages
3. Creates PR title and description following templates
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Optional

from titan_cli.core.logging import get_logger
from titan_cli.core.diffs import (
    SAMPLED_DIFF_NOTE,
    budget_diff_across_files,
    format_file_summary,
)
from titan_cli.ai.agents.base import BaseAIAgent, AgentRequest
from titan_cli.core.result import ClientSuccess, ClientError
from .config_loader import load_agent_config
from ..utils import calculate_pr_size, is_i18n_change

# Set up logger
logger = get_logger(__name__)


class PRStatus(StrEnum):
    """Outcome of the PR analysis portion of PRAgent."""

    OK = "ok"
    NO_COMMITS = "no_commits"
    SOURCE_DATA_FAILED = "source_data_failed"
    GENERATION_FAILED = "generation_failed"
    INCOMPLETE = "incomplete"


@dataclass
class PRAnalysis:
    """Complete analysis result from PRAgent."""

    # Commit analysis
    needs_commit: bool
    commit_message: Optional[str] = None
    staged_files: list[str] = None

    # PR analysis
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    pr_size: Optional[str] = None
    pr_status: PRStatus = PRStatus.OK
    pr_error: Optional[str] = None

    # Metadata
    total_tokens_used: int = 0
    branch_commits: list[str] = None
    files_changed: int = 0
    lines_changed: int = 0


class PRAgent(BaseAIAgent):
    """
    Platform-level agent for intelligent git workflow automation.

    This agent is the highest-level orchestrator that:
    - Analyzes the full context of a branch
    - Uses specialized agents (PRAgent) for specific tasks
    - Makes intelligent decisions about what actions to take
    - Generates all necessary content (commits, PRs)

    Example:
        ```python
        # In a workflow step
        pr_agent = PRAgent(ctx.ai, ctx.git, ctx.github)

        analysis = pr_agent.analyze_and_plan(
            head_branch="feat/new-feature",
            base_branch="main"
        )

        if analysis.needs_commit:
            # Use analysis.commit_message for commit

        if analysis.pr_title:
            # Use analysis.pr_title and analysis.pr_body for PR
        ```
    """

    def __init__(
        self,
        ai_client,
        git_client,
        github_client=None
    ):
        """
        Initialize PRAgent.

        Args:
            ai_client: The AIClient instance (provides AI capabilities)
            git_client: Git client for repository operations
            github_client: Optional GitHub client for PR operations
        """
        super().__init__(ai_client)
        self.git = git_client
        self.github = github_client

        # Load configuration from TOML (once per agent instance)
        self.config = load_agent_config("pr_agent")

    def get_system_prompt(self) -> str:
        """System prompt for platform-level orchestration (from config)."""
        # Use commit system prompt from config (Pydantic provides defaults)
        return self.config.commit_system_prompt

    def analyze_and_plan(
        self,
        head_branch: str,
        base_branch: Optional[str] = None,
        auto_stage: bool = False,
        additional_context: Optional[dict] = None
    ) -> PRAnalysis:
        """
        Analyze the complete branch context and create an execution plan.

        This is the main entry point. It:
        1. Checks repository status
        2. Determines if commit is needed
        3. Generates commit message if needed
        4. Analyzes branch for PR creation
        5. Generates PR title and description

        Args:
            head_branch: The branch to analyze
            base_branch: Base branch for comparison (defaults to main branch)
            auto_stage: Whether to analyze unstaged changes
            additional_context: Optional project-specific context (e.g., JIRA issues, test users)

        Returns:
            PRAnalysis with complete plan (gracefully handles errors)
        """
        base_branch = base_branch or self.git.main_branch
        total_tokens = 0

        # Initialize with safe defaults
        needs_commit = False
        commit_message = None
        staged_files = []
        pr_title = None
        pr_body = None
        pr_size = None
        pr_status = PRStatus.OK
        pr_error = None
        files_changed = 0
        lines_changed = 0
        commits = []

        # 1. Check if we need to commit (with error handling)
        try:
            status_result = self.git.get_status()
            match status_result:
                case ClientSuccess(data=status):
                    needs_commit = not status.is_clean

                    if needs_commit:
                        # Get unstaged/staged changes
                        try:
                            if auto_stage:
                                # Get modified files diff
                                diff_result = self.git.get_unstaged_diff()
                                match diff_result:
                                    case ClientSuccess(data=diff):
                                        # Also include untracked files if they exist
                                        if status.untracked_files:
                                            # Add header for untracked files context
                                            untracked_info = "\n\n# New untracked files:\n"
                                            for file in status.untracked_files:
                                                untracked_info += f"# - {file}\n"
                                            diff = diff + untracked_info if diff else untracked_info
                                    case ClientError(error_message=err):
                                        logger.error(f"Failed to get unstaged diff: {err}")
                                        diff = None
                            else:
                                diff_result = self.git.get_staged_diff()
                                match diff_result:
                                    case ClientSuccess(data=diff):
                                        pass  # diff is now extracted
                                    case ClientError(error_message=err):
                                        logger.error(f"Failed to get staged diff: {err}")
                                        diff = None

                            if diff:
                                # Generate commit message (with AI error handling)
                                try:
                                    commit_result = self._generate_commit_message(diff)
                                    commit_message = commit_result.message
                                    total_tokens += commit_result.tokens_used
                                except Exception as e:
                                    logger.warning(f"Failed to generate commit message: {e}")
                                    commit_message = None

                                # Get staged files
                                if status.staged_files:
                                    staged_files = status.staged_files

                        except Exception as e:
                            logger.error(f"Failed to get git diff: {e}")
                            # Continue with PR analysis even if commit analysis failed

                case ClientError(error_message=err):
                    logger.error(f"Failed to get git status: {err}")
                    # Continue with graceful fallback

        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            # Continue with graceful fallback

        # 2. Analyze branch for PR (with error handling)
        try:
            commits_result = self.git.get_branch_commits(base_branch, head_branch)
            diff_result = self.git.get_branch_diff(base_branch, head_branch)

            match (commits_result, diff_result):
                case (ClientSuccess(data=commits_data), ClientSuccess(data=branch_diff)):
                    commits = commits_data or []

                    if not commits or not branch_diff:
                        pr_status = PRStatus.NO_COMMITS
                    else:
                        # Read PR template (uses embedded default if file not found)
                        template = self._read_pr_template()

                        # Generate PR description (with AI error handling)
                        try:
                            pr_result = self._generate_pr_description(
                                commits=commits,
                                diff=branch_diff,
                                head_branch=head_branch,
                                base_branch=base_branch,
                                template=template,
                                additional_context=additional_context
                            )

                            pr_title = pr_result["title"]
                            pr_body = pr_result["body"]
                            pr_size = pr_result["pr_size"]
                            files_changed = pr_result["files_changed"]
                            lines_changed = pr_result["lines_changed"]
                            total_tokens += pr_result["tokens_used"]

                            if not pr_title or not pr_body:
                                pr_status = PRStatus.INCOMPLETE
                            else:
                                pr_status = PRStatus.OK

                        except Exception as e:
                            logger.error(f"Failed to generate PR description: {e}")
                            pr_status = PRStatus.GENERATION_FAILED
                            pr_error = str(e)

                case _:
                    logger.error("Failed to get branch commits or diff")
                    pr_status = PRStatus.SOURCE_DATA_FAILED
                    pr_error = "Failed to get branch commits or diff."

        except Exception as e:
            logger.error(f"Failed to analyze branch for PR: {e}")
            pr_status = PRStatus.SOURCE_DATA_FAILED
            pr_error = str(e)

        return PRAnalysis(
            needs_commit=needs_commit,
            commit_message=commit_message,
            staged_files=staged_files,
            pr_title=pr_title,
            pr_body=pr_body,
            pr_size=pr_size,
            pr_status=pr_status,
            pr_error=pr_error,
            total_tokens_used=total_tokens,
            branch_commits=commits,
            files_changed=files_changed,
            lines_changed=lines_changed
        )

    def _generate_commit_message(self, diff: str) -> "CommitMessageResult":
        """
        Generate a commit message from a diff (using config).

        Args:
            diff: The git diff to analyze

        Returns:
            CommitMessageResult with message and tokens

        Raises:
            ValueError: If diff is empty or AI response is invalid
            Exception: If AI generation fails
        """
        if not diff or not diff.strip():
            raise ValueError("Cannot generate commit message from empty diff")

        # Share the budget across files rather than keeping the head of the diff: the first
        # files git emits are not the important ones, and a message that describes only them
        # is wrong in a way nobody can see from reading it.
        max_diff = self.config.max_diff_size
        diff_preview = budget_diff_across_files(diff, max_diff)
        file_summary = format_file_summary(diff)
        sampled = SAMPLED_DIFF_NOTE if len(diff_preview) < len(diff) else ""

        prompt = f"""Analyze this diff and generate a conventional commit message.

## Changed files, with lines added and removed
{file_summary or "(no per-file information available)"}

{sampled}
```diff
{diff_preview}
```

Use format: type: Description (e.g., "feat: Add user authentication", "fix: Resolve memory leak")

Format your response EXACTLY like this:
COMMIT_MESSAGE: <conventional commit message>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=500,  # Increased from 200 to handle larger diffs
            system_prompt=self.config.commit_system_prompt,  # Use specific commit prompt
            operation="commit_message",
        )

        try:
            response = self.generate(request)
        except Exception as e:
            logger.error(f"AI generation failed for commit message: {e}")
            raise

        # Parse response
        message = response.content.replace("COMMIT_MESSAGE:", "").strip()
        message = message.strip('"').strip("'")

        # Validate message
        if not message or len(message.strip()) < 3:
            raise ValueError("AI generated invalid or empty commit message")

        # Truncate if too long
        if len(message) > 72:
            message = message[:69] + "..."

        return CommitMessageResult(
            message=message,
            tokens_used=response.tokens_used
        )

    def _generate_pr_description(
        self,
        commits: list[str],
        diff: str,
        head_branch: str,
        base_branch: str,
        template: Optional[str],
        additional_context: Optional[dict] = None
    ) -> dict:
        """
        Generate PR title and description using AI.

        Args:
            commits: List of commit messages
            diff: Full branch diff
            head_branch: Head branch name
            base_branch: Base branch name
            template: Optional PR template
            additional_context: Optional project-specific context

        Returns:
            Dict with keys: title, body, pr_size, files_changed, lines_changed, tokens_used

        Raises:
            ValueError: If commits/diff are empty or AI response is invalid
            Exception: If AI generation fails
        """
        # Validate inputs
        if not commits:
            raise ValueError("Cannot generate PR description without commits")
        if not diff or not diff.strip():
            raise ValueError("Cannot generate PR description from empty diff")

        # Calculate PR size
        estimation = calculate_pr_size(diff)
        pr_size = estimation.pr_size
        max_chars = estimation.max_chars
        files_changed = estimation.files_changed
        lines_changed = estimation.diff_lines

        # Build prompt
        prompt = self._build_pr_prompt(
            commits=commits,
            diff=diff,
            head_branch=head_branch,
            base_branch=base_branch,
            template=template,
            pr_size=pr_size,
            max_chars=max_chars,
            additional_context=additional_context
        )

        # Calculate max_tokens for OUTPUT (PR description generation)
        # max_tokens controls the response length, not input length
        # Scale based on PR size to provide appropriate detail level
        if pr_size == "small":
            max_tokens = 1500  # Brief summary + key changes
        elif pr_size == "medium":
            max_tokens = 3000  # Moderate detail
        elif pr_size == "large":
            max_tokens = 5000  # Comprehensive overview
        else:  # very large
            max_tokens = 8000  # Full context + migration notes

        # Add buffer for title + formatting overhead
        max_tokens = min(max_tokens + 500, 8000)

        # Generate with AI
        request = AgentRequest(
            context=prompt,
            max_tokens=max_tokens,
            system_prompt=self.config.pr_system_prompt,
            operation="pr_description",
        )

        try:
            response = self.generate(request)
        except Exception as e:
            logger.error(f"AI generation failed for PR description: {e}")
            raise

        # Parse response
        title, body = self._parse_pr_response(response.content, max_chars)

        return {
            "title": title,
            "body": body,
            "pr_size": pr_size,
            "files_changed": files_changed,
            "lines_changed": lines_changed,
            "tokens_used": response.tokens_used
        }


    def _build_pr_prompt(
        self,
        commits: list[str],
        diff: str,
        head_branch: str,
        base_branch: str,
        template: Optional[str],
        pr_size: str,
        max_chars: int,
        additional_context: Optional[dict] = None
    ) -> str:
        """Build the prompt for PR generation."""
        # Prepare commits text
        commits_text = "\n".join([f"  - {c}" for c in commits[:self.config.max_commits_to_analyze]])
        if len(commits) > self.config.max_commits_to_analyze:
            commits_text += f"\n  ... and {len(commits) - self.config.max_commits_to_analyze} more commits"

        # A PR description has to cover the whole change, so every file gets a share of the
        # budget and the per-file counts always travel in full - see the summary section in
        # the prompt below.
        max_diff = self.config.max_diff_size
        diff_preview = budget_diff_across_files(diff, max_diff) if diff else "No diff available"
        # A PR body is expected to state the scope of the change, so it lists more files
        # than a one-line commit subject ever needs to.
        diff_file_summary = format_file_summary(diff, max_files=150) if diff else ""
        diff_sampled_note = SAMPLED_DIFF_NOTE if diff and len(diff_preview) < len(diff) else ""

        # Detect special change types and add context
        special_context = ""
        if is_i18n_change(diff):
            special_context = """
**IMPORTANT - Localization/i18n Changes Detected:**
This PR modifies localization/translation files. When analyzing:
- Focus on WHAT user-facing text changed (use key/id names as hints for location)
- Explain WHY the text changed (typo fix, UX improvement, rebranding, etc.)
- Look at commit messages for business context
- If the same change appears across multiple language files, treat it as ONE logical change
- Describe the change from a user perspective, not just "updated strings"

"""

        # Format additional context (project-specific info)
        project_context = ""
        if additional_context:
            project_context = "\n<project_context>\n"
            for key, value in additional_context.items():
                if value:  # Only include non-empty values
                    # Sanitize: limit length and basic validation
                    sanitized_value = str(value)[:500]  # Max 500 chars per field
                    project_context += f"{key}: {sanitized_value}\n"
            project_context += "</project_context>\n\n"

        # Build prompt with template (always available - either from file or embedded default)
        return f"""{special_context}{project_context}Analyze this branch and generate a professional pull request following the EXACT template structure.

## Branch Information
- Head branch: {head_branch}
- Base branch: {base_branch}
- Total commits: {len(commits)}

## Commits in Branch
{commits_text}

## Files Changed, with lines added and removed
{diff_file_summary or "(no per-file information available)"}

## Branch Diff Preview
{diff_sampled_note}
```diff
{diff_preview}
```

## PR Template (MUST FOLLOW THIS STRUCTURE)
```markdown
{template}
```

## CRITICAL Instructions
1. **Title**: Follow conventional commits format WITHOUT scope (type: Description), be clear and descriptive
   - Format: `type: Description` (NO scope, NO parentheses)
   - **HARD LIMIT: title MUST be ≤72 characters total** (count carefully before writing)
   - Start description with CAPITAL letter (imperative mood)
   - **If <project_context> contains issue IDs** (e.g., jira_issues, issue_ids, tickets), include them in the title BEFORE the description:
     * Format: `type: ISSUE-1, ISSUE-2 Description`
     * Example: `feat: PROJ-1234, PROJ-5678 Add OAuth2 integration`
   - Examples without issues: "feat: Add user auth flow", "fix: Resolve cache race condition"
   - NEVER use format like "feat(scope): Description" - always use "feat: Description"

2. **Change prioritization** — focus on what matters most:
   - **Primary**: source code changes (`.py`, `.ts`, `.kt`, `.swift`, etc.) — these describe WHAT was built or fixed
   - **Secondary**: config files, YAML, tests — include only if meaningfully distinct from code changes
   - **Ignore for title/summary**: `.md` files, `docs/`, `CLAUDE.md`, changelogs — documentation is supplementary
   - If the branch adds a feature AND updates docs, the **title and summary must describe the feature**, not the documentation

3. **Project Context**: If <project_context> is provided above, incorporate information into appropriate sections:
   - **Issue IDs** (jira_issues, etc.): Include in TITLE (see instruction 1) AND in the body if the template has a section for it (e.g., "Related Issues", "JIRA", etc.)
   - **test_info**: Add to the "Testing" or "Test plan" section (users, credentials, steps)
   - **related_pr**: Add to "Additional Notes" or similar section

4. **Description**: MUST follow the template structure above but keep it under {max_chars} characters total
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

    def _parse_pr_response(self, content: str, max_chars: int) -> tuple[str, str]:
        """
        Parse AI response to extract title and description.

        Handles various AI response formats (case-insensitive, with or without preamble).

        Returns:
            Tuple of (title, description)
        """
        # Normalize content for case-insensitive matching
        content_upper = content.upper()
        title_idx = content_upper.find("TITLE:")
        desc_idx = content_upper.find("DESCRIPTION:")

        if title_idx == -1 or desc_idx == -1:
            raise ValueError(
                f"AI response format incorrect. Expected 'TITLE:' and 'DESCRIPTION:' sections.\n"
                f"Got: {content[:200]}..."
            )

        # Extract title and description using original content (preserves casing)
        title = content[title_idx + 6:desc_idx].strip()  # +6 for len("TITLE:")
        description = content[desc_idx + 12:].strip()  # +12 for len("DESCRIPTION:")

        # Clean up title (remove quotes if present)
        title = title.strip('"').strip("'")

        # Ensure title subject starts with capital letter (conventional commits requirement)
        # Format: type: Description
        if ':' in title:
            parts = title.split(':', 1)
            if len(parts) == 2:
                prefix = parts[0]  # type
                subject = parts[1].strip()  # description
                # Capitalize first letter of subject
                if subject and subject[0].islower():
                    subject = subject[0].upper() + subject[1:]
                title = f"{prefix}: {subject}"

        # Validate description
        if not description or len(description.strip()) < 10:
            raise ValueError("AI generated an empty or incomplete PR description")

        return title, description

    def _read_pr_template(self) -> str:
        """
        Read PR template if configured, otherwise use embedded default.

        Only reads from file if pr_template_path is explicitly configured.
        If not configured or file doesn't exist, uses embedded default template.

        Returns:
            Template content (never None - uses embedded default if needed)
        """
        # Check if template path is configured
        if self.github and hasattr(self.github, 'config'):
            config_path = self.github.config.pr_template_path
            if config_path:  # Template path is configured
                path = Path(config_path)
                if path.exists():
                    try:
                        with open(path, "r") as f:
                            return f.read()
                    except Exception:
                        pass  # Fall through to default template

        # No template configured or file not found - use embedded default
        return self._get_default_template()

    def _get_default_template(self) -> str:
        """
        Get the default PR template when no file exists.

        This template provides a structured format that adapts to PR size
        and encourages comprehensive documentation.

        Returns:
            Default markdown template
        """
        return """## Summary
Brief overview of what changed and why.

## Changes Made
- Key change 1
- Key change 2
- Key change 3

## Testing
How to verify these changes work.

## Additional Notes
Any additional context, screenshots, or breaking changes.
"""


@dataclass
class CommitMessageResult:
    """Result from commit message generation."""
    message: str
    tokens_used: int
