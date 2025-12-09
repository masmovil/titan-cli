# titan_cli/ai/agents/platform_agent.py
"""
PlatformAgent - Intelligent orchestrator for git workflows.

This agent analyzes the complete context of a branch and automatically:
1. Determines if changes need to be committed
2. Generates appropriate commit messages
3. Creates PR title and description following templates
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .base import BaseAIAgent, AgentRequest
from .config import get_agent_config

if TYPE_CHECKING:
    from titan_cli.ai.client import AIClient
    from titan_cli.clients.git_client import GitClient
    from titan_cli.clients.github_client import GitHubClient


@dataclass
class PlatformAnalysis:
    """Complete analysis result from PlatformAgent."""

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


class PlatformAgent(BaseAIAgent):
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
        platform_agent = PlatformAgent(ctx.ai, ctx.git, ctx.github)

        analysis = platform_agent.analyze_and_plan(
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
        ai_client: "AIClient",
        git_client: "GitClient",
        github_client: Optional["GitHubClient"] = None
    ):
        """
        Initialize PlatformAgent.

        Args:
            ai_client: The AIClient instance (provides AI capabilities)
            git_client: Git client for repository operations
            github_client: Optional GitHub client for PR operations
        """
        super().__init__(ai_client)
        self.git = git_client
        self.github = github_client

        # Load configuration from TOML
        self.config = get_agent_config("platform_agent")

    def get_system_prompt(self) -> str:
        """System prompt for platform-level orchestration (from config)."""
        # Default to commit system prompt for platform-level operations
        return self.config.commit_system_prompt or """You are a platform automation expert. You analyze git repositories
and provide intelligent suggestions for commits and pull requests. You understand
conventional commits, best practices, and can make decisions about repository state."""

    def analyze_and_plan(
        self,
        head_branch: str,
        base_branch: Optional[str] = None,
        auto_stage: bool = False
    ) -> PlatformAnalysis:
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
            PlatformAnalysis with complete plan
        """
        base_branch = base_branch or self.git.main_branch
        total_tokens = 0

        # 1. Check if we need to commit
        status = self.git.get_status()
        needs_commit = not status.is_clean
        commit_message = None
        staged_files = []

        if needs_commit:
            # Get unstaged/staged changes
            if auto_stage:
                # Analyze working directory changes
                diff = self.git.get_diff(staged=False)
            else:
                # Analyze only staged changes
                diff = self.git.get_diff(staged=True)

            if diff:
                # Generate commit message
                commit_result = self._generate_commit_message(diff)
                commit_message = commit_result.message
                total_tokens += commit_result.tokens_used

                # Get staged files
                if status.staged_files:
                    staged_files = status.staged_files

        # 2. Analyze branch for PR
        commits = self.git.get_branch_commits(base_branch, head_branch)
        branch_diff = self.git.get_branch_diff(base_branch, head_branch)

        pr_title = None
        pr_body = None
        pr_size = None
        files_changed = 0
        lines_changed = 0

        if branch_diff and commits:
            # Read PR template
            template = self._read_pr_template()

            # Generate PR description
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

        return PlatformAnalysis(
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
        """
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
            temperature=self.config.temperature,
            system_prompt=self.config.commit_system_prompt  # Use specific commit prompt
        )

        response = self.generate(request)

        # Parse response
        message = response.content.replace("COMMIT_MESSAGE:", "").strip()
        message = message.strip('"').strip("'")

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
        """
        # Calculate PR size
        pr_size, max_chars, files_changed, lines_changed = self._calculate_pr_size(diff)

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
        max_tokens = min(estimated_tokens, self.config.max_tokens)

        # Generate with AI
        request = AgentRequest(
            context=prompt,
            max_tokens=max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.pr_system_prompt
        )

        response = self.generate(request)

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

    def _calculate_pr_size(self, diff: str) -> tuple[str, int, int, int]:
        """
        Calculate PR size and determine character limits (from config).

        Returns:
            Tuple of (size_label, max_chars, files_changed, lines_changed)
        """
        lines_changed = len(diff.split('\n'))

        # Count files changed
        file_pattern = r'^diff --git'
        files_changed = len(re.findall(file_pattern, diff, re.MULTILINE))

        # Determine size and character limit (from config)
        if files_changed <= 3 and lines_changed < 100:
            return "small", self.config.small_pr_max_chars, files_changed, lines_changed
        elif files_changed <= 10 and lines_changed < 500:
            return "medium", self.config.medium_pr_max_chars, files_changed, lines_changed
        elif files_changed <= 30 and lines_changed < 2000:
            return "large", self.config.large_pr_max_chars, files_changed, lines_changed
        else:
            return "very large", self.config.very_large_pr_max_chars, files_changed, lines_changed

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
