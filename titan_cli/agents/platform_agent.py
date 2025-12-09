"""
Platform Agent - Dual Mode Support

Platform engineering agent that can run in two modes:
1. Interactive Mode: AI executes tools autonomously (TAP)
2. Analysis Mode: AI analyzes pre-computed data (workflow step)

Example Interactive:
    agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
    result = agent.run(ctx, mode="interactive")

Example Analysis:
    workflow = BaseWorkflow(steps=[
        get_git_status_step,
        platform_agent_analysis_step
    ])
"""

from pathlib import Path
from typing import Optional
import sys

# Use tomli for Python < 3.11, tomllib for Python >= 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback if tomli not installed
        import tomllib

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip


class PlatformAgent:
    """
    Platform engineering agent with dual mode support.

    Modes:
    - interactive: AI decides which tools to execute (requires TAP)
    - analysis: AI analyzes data from ctx.data (no tool execution)

    The analysis mode allows using the agent as a workflow step.
    """

    def __init__(self, config: dict, config_path: Optional[Path] = None):
        """
        Initialize agent with configuration.

        Args:
            config: Agent configuration dictionary from TOML
            config_path: Path to config file (for reference)
        """
        self.config = config
        self.config_path = config_path
        self.name = config['agent']['name']
        self.description = config['agent']['description']

    @classmethod
    def from_toml(cls, config_path: str | Path) -> 'PlatformAgent':
        """
        Load agent from TOML configuration file.

        Args:
            config_path: Path to TOML config file

        Returns:
            PlatformAgent instance

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Agent config not found: {config_path}")

        with open(path, 'rb') as f:
            config = tomllib.load(f)

        return cls(config, path)

    def run(
        self,
        ctx: WorkflowContext,
        user_context: str = "",
        mode: str = "analysis"
    ) -> WorkflowResult:
        """
        Run the agent in specified mode.

        Args:
            ctx: Workflow context with dependencies
            user_context: User instructions/prompt
            mode: "interactive" (with tools) or "analysis" (without tools)

        Returns:
            WorkflowResult (Success, Error, or Skip)
        """
        if mode == "interactive":
            return self._run_interactive_mode(ctx, user_context)
        elif mode == "analysis":
            return self._run_analysis_mode(ctx, user_context)
        else:
            return Error(f"Invalid mode: {mode}. Use 'interactive' or 'analysis'")

    def _run_interactive_mode(
        self,
        ctx: WorkflowContext,
        user_context: str
    ) -> WorkflowResult:
        """
        Interactive mode: AI executes tools autonomously.

        This mode requires TAP integration (not implemented in this branch).
        Will be fully implemented when merging with feat/platform-agent.

        Returns:
            Error: TAP not available in this branch
        """
        return Error(
            "Interactive mode requires TAP integration. "
            "Use analysis mode or wait for feat/platform-agent merge."
        )

    def _run_analysis_mode(
        self,
        ctx: WorkflowContext,
        user_context: str
    ) -> WorkflowResult:
        """
        Analysis mode: AI analyzes data from ctx.data.

        This mode reads pre-computed data (populated by previous workflow steps)
        and uses AI to analyze it without executing any tools.

        Args:
            ctx: Workflow context
            user_context: Task description

        Returns:
            Success: With AI analysis
            Skip: If no AI or no data
            Error: If AI generation fails
        """
        # Check AI availability
        if not ctx.ai:
            return Skip("AI not configured, skipping analysis")

        # Extract data from context
        analysis_data = self._extract_context_data(ctx)

        if not analysis_data:
            return Skip("No data in context to analyze")

        # Build analysis prompt
        prompt = self._build_analysis_prompt(analysis_data, user_context)

        # Get system prompt
        system_prompt = self._get_analysis_system_prompt()

        # Call AI (no tools - pure analysis)
        try:
            response = ctx.ai.generate(
                prompt=prompt,
                system_prompt=system_prompt
            )

            return Success(
                response,
                metadata={
                    "mode": "analysis",
                    "agent": self.name,
                    "data_keys": list(analysis_data.keys())
                }
            )

        except Exception as e:
            return Error(f"AI analysis failed: {e}", exception=e)

    def _extract_context_data(self, ctx: WorkflowContext) -> dict:
        """
        Extract relevant data from ctx.data for analysis.

        Looks for common workflow data like git_status, git_diff, etc.

        Args:
            ctx: Workflow context

        Returns:
            Dictionary with extracted data
        """
        data = {}

        # Git status (from get_git_status_step)
        if "git_status" in ctx.data:
            status = ctx.data["git_status"]
            data["git_status"] = {
                "branch": getattr(status, 'branch', ''),
                "modified": getattr(status, 'modified_files', []),
                "untracked": getattr(status, 'untracked_files', []),
                "is_clean": getattr(status, 'is_clean', False)
            }

        # Git diff (if available)
        if "git_diff" in ctx.data:
            data["git_diff"] = ctx.data["git_diff"]

        # Commit info
        if "commit_message" in ctx.data:
            data["commit_info"] = {
                "message": ctx.data["commit_message"],
                "hash": ctx.data.get("commit_hash")
            }

        # PR info
        if "pr_number" in ctx.data:
            data["pr_info"] = {
                "number": ctx.data.get("pr_number"),
                "title": ctx.data.get("pr_title"),
                "body": ctx.data.get("pr_body"),
                "url": ctx.data.get("pr_url")
            }

        # Files changed
        if "files_changed" in ctx.data:
            data["files_changed"] = ctx.data["files_changed"]

        return data

    def _build_analysis_prompt(self, data: dict, user_context: str) -> str:
        """
        Build analysis prompt from context data.

        Args:
            data: Extracted context data
            user_context: User task description

        Returns:
            Formatted prompt string
        """
        parts = []

        # Add user context first
        if user_context:
            parts.append(f"{user_context}\n\n")
        else:
            parts.append("Analyze the following data:\n\n")

        # Git status section
        if "git_status" in data:
            status = data["git_status"]
            parts.append("## Repository Status\n\n")
            parts.append(f"- Branch: {status['branch']}\n")
            parts.append(f"- Clean: {status['is_clean']}\n")

            if not status['is_clean']:
                if status['modified']:
                    parts.append(f"- Modified files: {len(status['modified'])}\n")
                    for file in status['modified'][:15]:
                        parts.append(f"  - {file}\n")

                if status['untracked']:
                    parts.append(f"- Untracked files: {len(status['untracked'])}\n")

            parts.append("\n")

        # Git diff section
        if "git_diff" in data:
            diff = data["git_diff"]
            # Limit diff size to avoid token overflow
            max_diff_length = 3000
            if len(diff) > max_diff_length:
                diff = diff[:max_diff_length] + "\n... (truncated)"

            parts.append("## Changes\n\n")
            parts.append(f"```diff\n{diff}\n```\n\n")

        # Commit info section
        if "commit_info" in data:
            commit = data["commit_info"]
            parts.append("## Commit Info\n\n")
            if commit.get("message"):
                parts.append(f"- Message: {commit['message']}\n")
            if commit.get("hash"):
                parts.append(f"- Hash: {commit['hash']}\n")
            parts.append("\n")

        # PR info section
        if "pr_info" in data:
            pr = data["pr_info"]
            parts.append("## Pull Request\n\n")
            if pr.get("number"):
                parts.append(f"- Number: #{pr['number']}\n")
            if pr.get("title"):
                parts.append(f"- Title: {pr['title']}\n")
            if pr.get("url"):
                parts.append(f"- URL: {pr['url']}\n")
            parts.append("\n")

        return "".join(parts)

    def _get_analysis_system_prompt(self) -> str:
        """
        Get system prompt for analysis mode.

        Checks TOML config for analysis-specific prompt,
        falls back to regular system prompt.

        Returns:
            System prompt string
        """
        prompts = self.config.get("prompts", {})

        # Try analysis-specific prompt
        if "analysis_system" in prompts:
            return prompts["analysis_system"]

        # Fallback to regular system prompt
        if "system" in prompts:
            return prompts["system"]

        # Default fallback
        return """You are a Platform Engineering expert.
Analyze the provided data and give concise, actionable insights."""

    def get_system_prompt(self) -> str:
        """Get standard system prompt from config."""
        return self.config.get("prompts", {}).get(
            "system",
            "You are a Platform Engineering expert assistant."
        )

    def get_user_prompt(self, context: str = "") -> str:
        """Get user prompt from config with context substitution."""
        template = self.config.get("prompts", {}).get(
            "user_template",
            "{context}"
        )
        return template.format(context=context)
