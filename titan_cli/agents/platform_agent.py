"""
Platform Agent - TAP + TOML Configuration

Platform engineering agent for automating Git, GitHub, and development workflows.

This agent demonstrates TAP implementation:
- TOML-based configuration (consistent with project standards)
- TAP tools for AI decision-making
- Framework-agnostic architecture
- Extensible for platform engineering tasks
"""

from pathlib import Path
from typing import List, Any, Optional
import sys

# Use tomli for Python < 3.11, tomllib for Python >= 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from dataclasses import dataclass, field
from typing import Dict

from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error
from titan_cli.tap.manager import AdapterManager


# TAP Tool definitions (same as in GitHub plugin)
@dataclass
class ToolParameter:
    """Metadata for a tool parameter."""
    type_hint: str
    description: str = ""
    required: bool = True


@dataclass
class ToolSchema:
    """Schema definition for a tool."""
    name: str
    description: str
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)


class TitanTool:
    """Base class for Titan tools."""

    def __init__(self, schema: ToolSchema):
        self.schema = schema
        self.name = schema.name
        self.description = schema.description

    def execute(self, **kwargs) -> Any:
        """Execute the tool - to be overridden."""
        raise NotImplementedError


class PlatformAgent:
    """
    Platform engineering agent using TAP + TOML configuration.

    Architecture:
    - Configuration loaded from TOML file (consistent with project standards)
    - TAP tools for AI to use autonomously
    - AI provider via TAP adapter (framework-agnostic)
    - Extensible for Git, GitHub, CI/CD, and automation workflows

    Example:
        ctx = WorkflowContext(git=git_client, ai=ai_client, ui=ui_client)
        agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
        result = agent.run(ctx)
    """

    def __init__(
        self,
        config: dict,
        config_path: Optional[Path] = None
    ):
        """
        Initialize agent with configuration.

        Args:
            config: Agent configuration dictionary
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
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Agent config not found: {config_path}")

        with open(path, 'rb') as f:
            config = tomllib.load(f)

        return cls(config, path)

    def get_tap_tools(self, ctx: WorkflowContext) -> List[TitanTool]:
        """
        Get TAP tools defined in TOML configuration.

        Args:
            ctx: Workflow context with Git client

        Returns:
            List of TitanTool instances
        """
        tools = []

        for tool_config in self.config['tap']['tools']:
            if not tool_config.get('enabled', True):
                continue

            tool_name = tool_config['name']

            # Map tool names to implementations
            if tool_name == 'get_git_status':
                tools.append(GetGitStatusTool(ctx.git))
            elif tool_name == 'analyze_git_diff':
                tools.append(AnalyzeGitDiffTool(ctx.git))
            elif tool_name == 'create_commit':
                tools.append(CreateCommitTool(ctx.git))

        return tools

    def get_system_prompt(self) -> str:
        """Get system prompt from configuration."""
        return self.config.get('prompts', {}).get('system', '')

    def get_user_prompt(self, context: str = "") -> str:
        """
        Get user prompt from configuration template.

        Args:
            context: Additional context to include

        Returns:
            Formatted user prompt
        """
        template = self.config.get('prompts', {}).get('user_template', '{context}')
        return template.format(context=context)

    def run(self, ctx: WorkflowContext, user_context: str = "") -> WorkflowResult:
        """
        Run the agent using TAP.

        Args:
            ctx: Workflow context
            user_context: Additional context for the user prompt

        Returns:
            WorkflowResult with execution outcome
        """
        if ctx.ui and ctx.ui.text:
            ctx.ui.text.title(f"🤖 {self.name}")
            ctx.ui.text.info(self.description)
            ctx.ui.text.line()

        try:
            # Get TAP tools
            tools = self.get_tap_tools(ctx)

            if ctx.ui and ctx.ui.text:
                ctx.ui.text.info(f"📦 Loaded {len(tools)} TAP tools")

            # Get TAP adapter (provider-agnostic)
            provider = self.config['tap']['provider']
            adapter_manager = AdapterManager.from_config("config/tap/adapters.yml")
            adapter = adapter_manager.get(provider)

            if ctx.ui and ctx.ui.text:
                ctx.ui.text.info(f"🔌 Using provider: {provider}")

            # Convert tools to provider format
            provider_tools = adapter.convert_tools(tools)

            # Get prompts
            system_prompt = self.get_system_prompt()
            user_prompt = self.get_user_prompt(user_context)

            if ctx.ui and ctx.ui.text:
                ctx.ui.text.line()
                ctx.ui.text.info("🧠 AI analyzing changes...")

            # AI decides which tools to use
            response = ctx.ai.generate_with_tools(
                prompt=user_prompt,
                tools=provider_tools,
                system_prompt=system_prompt
            )

            if ctx.ui and ctx.ui.text:
                ctx.ui.text.line()
                ctx.ui.text.success("✅ Agent completed successfully")

            return Success(
                "Agent execution completed",
                metadata={
                    'agent': self.name,
                    'provider': provider,
                    'tools_used': len(tools),
                    'response': response
                }
            )

        except Exception as e:
            if ctx.ui and ctx.ui.text:
                ctx.ui.text.error(f"❌ Agent failed: {e}")

            return Error(
                f"Agent execution failed: {e}",
                exception=e
            )


# ================================================================
# TAP TOOLS IMPLEMENTATIONS
# ================================================================

class GetGitStatusTool(TitanTool):
    """TAP tool for getting Git status."""

    def __init__(self, git_client):
        schema = ToolSchema(
            name="get_git_status",
            description="Gets the current status of the Git repository including modified files, branch, and staging area",
            parameters={}
        )
        super().__init__(schema)
        self.git_client = git_client

    def execute(self) -> str:
        """Execute tool and return formatted status."""
        status = self.git_client.get_status()

        result = []
        result.append(f"Branch: {status.branch}")

        if status.modified_files:
            result.append(f"\nModified files ({len(status.modified_files)}):")
            for file in status.modified_files:
                result.append(f"  - {file}")

        if status.staged_files:
            result.append(f"\nStaged files ({len(status.staged_files)}):")
            for file in status.staged_files:
                result.append(f"  - {file}")

        if status.untracked_files:
            result.append(f"\nUntracked files ({len(status.untracked_files)}):")
            for file in status.untracked_files[:5]:  # Limit to 5
                result.append(f"  - {file}")
            if len(status.untracked_files) > 5:
                result.append(f"  ... and {len(status.untracked_files) - 5} more")

        return "\n".join(result)


class AnalyzeGitDiffTool(TitanTool):
    """TAP tool for analyzing Git diff."""

    def __init__(self, git_client):
        schema = ToolSchema(
            name="analyze_git_diff",
            description="Analyzes the git diff to understand what changed in the code. Returns a summary of changes.",
            parameters={
                "file_path": {
                    "type": "string",
                    "description": "Optional: specific file to diff (if not provided, diffs all modified files)",
                    "required": False
                }
            }
        )
        super().__init__(schema)
        self.git_client = git_client

    def execute(self, file_path: Optional[str] = None) -> str:
        """Execute tool and return diff analysis."""
        if file_path:
            diff = self.git_client.diff(file_path)
            return f"Diff for {file_path}:\n{diff}"
        else:
            diff = self.git_client.diff()

            # Truncate if too long
            if len(diff) > 2000:
                return f"Diff (truncated to 2000 chars):\n{diff[:2000]}\n\n... (truncated)"

            return f"Diff:\n{diff}"


class CreateCommitTool(TitanTool):
    """TAP tool for creating Git commits."""

    def __init__(self, git_client):
        schema = ToolSchema(
            name="create_commit",
            description="Creates a Git commit with a conventional commit message. Files must be staged first.",
            parameters={
                "message": {
                    "type": "string",
                    "description": "Commit message in conventional commits format: type(scope): description",
                    "required": True
                },
                "files": {
                    "type": "array",
                    "description": "List of file paths to stage and commit",
                    "items": {"type": "string"},
                    "required": True
                }
            }
        )
        super().__init__(schema)
        self.git_client = git_client

    def execute(self, message: str, files: List[str]) -> str:
        """Execute tool and create commit."""
        # Stage files
        for file in files:
            self.git_client.add(file)

        # Create commit
        self.git_client.commit(message)

        # Get commit hash
        status = self.git_client.get_status()

        return f"✅ Commit created: {message}\nFiles: {', '.join(files)}"
