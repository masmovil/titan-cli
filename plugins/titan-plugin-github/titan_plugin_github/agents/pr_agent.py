# plugins/titan-plugin-github/titan_plugin_github/agents/pr_agent.py
"""
PRAgent - Intelligent orchestrator for git workflows.

This agent analyzes the complete context of a branch and automatically:
1. Determines if changes need to be committed
2. Generates appropriate commit messages
3. Creates PR title and description following templates
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from titan_cli.ai.agents.base import BaseAIAgent, AgentRequest
from .config_loader import load_agent_config
from ..utils import calculate_pr_size

# Set up logger
logger = logging.getLogger(__name__)


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
        auto_stage: bool = False
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
        files_changed = 0
        lines_changed = 0
        commits = []

        # 1. Check if we need to commit (with error handling)
        try:
            status = self.git.get_status()
            needs_commit = not status.is_clean

            if needs_commit:
                # Get unstaged/staged changes
                try:
                    if auto_stage:
                        # Get modified files diff
                        diff = self.git.get_unstaged_diff()

                        # Also include untracked files if they exist
                        if status.untracked_files:
                            # Add header for untracked files context
                            untracked_info = "\n\n# New untracked files:\n"
                            for file in status.untracked_files:
                                untracked_info += f"# - {file}\n"
                            diff = diff + untracked_info if diff else untracked_info
                    else:
                        diff = self.git.get_staged_diff()

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

        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            # Continue with graceful fallback

        # 2. Analyze branch for PR (with error handling)
        try:
            commits = self.git.get_branch_commits(base_branch, head_branch)
            branch_diff = self.git.get_branch_diff(base_branch, head_branch)

            if branch_diff and commits:
                # Read PR template (safe - returns None on error)
                template = self._read_pr_template()

                # Generate PR description (with AI error handling)
                try:
                    pr_result = self._generate_pr_description(
                        commits=commits,
                        diff=branch_diff,
                        head_branch=head_branch,
                        base_branch=base_branch,
                        template=template
                    )

                    pr_title = pr_result["title"]
                    pr_body = pr_result["body"]
                    pr_size = pr_result["pr_size"]
                    files_changed = pr_result["files_changed"]
                    lines_changed = pr_result["lines_changed"]
                    total_tokens += pr_result["tokens_used"]

                except Exception as e:
                    logger.error(f"Failed to generate PR description: {e}")
                    # Return analysis without PR data

        except Exception as e:
            logger.error(f"Failed to analyze branch for PR: {e}")
            # Return analysis without PR data

        return PRAnalysis(
            needs_commit=needs_commit,
            commit_message=commit_message,
            staged_files=staged_files,
            pr_title=pr_title,
            pr_body=pr_body,
            pr_size=pr_size,
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

        # Truncate diff if too large (from config)
        max_diff = self.config.max_diff_size
        diff_preview = diff[:max_diff]
        if len(diff) > max_diff:
            diff_preview += "\n\n... (diff truncated)"

        prompt = f"""Analyze this diff and generate a conventional commit message.

```diff
{diff_preview}
```

Format your response EXACTLY like this:
COMMIT_MESSAGE: <conventional commit message>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=200,
            system_prompt=self.config.commit_system_prompt  # Use specific commit prompt
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
        template: Optional[str]
    ) -> dict:
        """
        Generate PR title and description using AI.

        Args:
            commits: List of commit messages
            diff: Full branch diff
            head_branch: Head branch name
            base_branch: Base branch name
            template: Optional PR template

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
            max_chars=max_chars
        )

        # Calculate tokens
        estimated_tokens = int(max_chars * 0.75) + 200
        max_tokens = min(estimated_tokens, 4000)  # Cap at 4000 tokens

        # Generate with AI
        request = AgentRequest(
            context=prompt,
            max_tokens=max_tokens,
            system_prompt=self.config.pr_system_prompt
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
        max_chars: int
    ) -> str:
        """Build the prompt for PR generation."""
        # Prepare commits text
        commits_text = "\n".join([f"  - {c}" for c in commits[:self.config.max_commits_to_analyze]])
        if len(commits) > self.config.max_commits_to_analyze:
            commits_text += f"\n  ... and {len(commits) - self.config.max_commits_to_analyze} more commits"

        # Limit diff size
        max_diff = self.config.max_diff_size
        diff_preview = diff[:max_diff] if diff else "No diff available"
        if len(diff) > max_diff:
            diff_preview += "\n\n... (diff truncated for brevity)"

        # Build prompt based on template availability
        if template:
            return f"""Analyze this branch and generate a professional pull request following the EXACT template structure.

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
            return f"""Analyze this branch and generate a professional pull request.

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

    def _parse_pr_response(self, content: str, max_chars: int) -> tuple[str, str]:
        """
        Parse AI response to extract title and description.

        Returns:
            Tuple of (title, description)
        """
        if "TITLE:" not in content or "DESCRIPTION:" not in content:
            raise ValueError(
                f"AI response format incorrect. Expected 'TITLE:' and 'DESCRIPTION:' sections.\n"
                f"Got: {content[:200]}..."
            )

        # Extract title and description
        parts = content.split("DESCRIPTION:", 1)
        title = parts[0].replace("TITLE:", "").strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        # Clean up title
        title = title.strip('"').strip("'")

        # Truncate title if too long
        if len(title) > 72:
            title = title[:69] + "..."

        # Truncate description if needed
        if len(description) > max_chars:
            description = description[:max_chars - 3] + "..."

        # Validate description
        if not description or len(description.strip()) < 10:
            raise ValueError("AI generated an empty or incomplete PR description")

        return title, description

    def _read_pr_template(self, template_path: str = ".github/pull_request_template.md") -> Optional[str]:
        """
        Read PR template if it exists.

        Args:
            template_path: Path to the template file

        Returns:
            Template content or None
        """
        path = Path(template_path)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return None


@dataclass
class CommitMessageResult:
    """Result from commit message generation."""
    message: str
    tokens_used: int
