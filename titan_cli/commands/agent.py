"""
Agent Commands

CLI commands for running AI-powered autonomous agents.
"""

import typer
from pathlib import Path

from ..core.config import TitanConfig
from ..core.secrets import SecretManager
from ..engine import WorkflowContextBuilder, BaseWorkflow
from ..ui.components.typography import TextRenderer
from ..messages import msg


agent_app = typer.Typer(name="agent", help="Run AI-powered autonomous agents.")


@agent_app.command("auto-commit")
@agent_app.command("commit")  # Alias
def auto_commit(
    auto_confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt"
    ),
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Repository path (default: current directory)"
    )
):
    """
    Auto-commit: AI-powered automatic Git commits.

    Analyzes your code changes and generates meaningful conventional
    commit messages using AI.

    Example:
        titan agent auto-commit           # Interactive mode
        titan agent auto-commit --yes     # Auto-confirm
        titan agent auto-commit -p /path  # Custom repo path
    """
    text = TextRenderer()

    # Header
    text.title("🤖 Auto-Commit Agent")
    text.line()
    text.info("AI-powered automatic Git commit generation")
    text.line()

    # Initialize config
    config = TitanConfig()
    secrets = SecretManager()

    # Check AI configuration
    if not config.config.ai:
        text.error("❌ AI not configured. Run: titan ai configure")
        raise typer.Exit(1)

    # Build context with Git and AI
    try:
        context = (
            WorkflowContextBuilder(config=config, secrets=secrets)
            .with_git(repo_path=str(path))
            .with_ai()
            .with_ui()
            .build()
        )
    except Exception as e:
        text.error(f"❌ Failed to initialize: {e}")
        raise typer.Exit(1)

    # Set auto-confirm flag
    context.data["auto_confirm"] = auto_confirm

    # Import agent step (uses CascadeAgent base class)
    from ..agents.auto_commit_agent import auto_commit_step

    # Create workflow
    workflow = BaseWorkflow(
        name="Auto-Commit",
        steps=[auto_commit_step]
    )

    # Run workflow
    try:
        result = workflow.run(context)

        text.line()

        if result.success:
            text.success("✅ Commit created successfully!")

            # Show metadata
            if result.metadata:
                commit_msg = result.metadata.get("commit_message")
                method = result.metadata.get("method", "unknown")
                tokens = result.metadata.get("tokens_used", 0)
                files_count = result.metadata.get("files_count", result.metadata.get("files_committed", 0))

                text.line()
                text.info("📝 Commit Details:")
                text.body(f"Message: {commit_msg}", style="dim")
                text.body(f"Method: {method}", style="dim")

                if tokens > 0:
                    text.body(f"Tokens used: ~{tokens}", style="dim")
                else:
                    text.body(f"Tokens used: 0 (no AI needed!)", style="bold green")

                if files_count:
                    text.body(f"Files: {files_count}", style="dim")
        else:
            text.warning(f"⚠️  {result.message}")

    except KeyboardInterrupt:
        text.line()
        text.warning("⚠️  Cancelled by user")
        raise typer.Exit(0)
    except Exception as e:
        text.line()
        text.error(f"❌ Workflow failed: {e}")
        raise typer.Exit(1)


@agent_app.command("platform")
def platform_agent(
    auto_confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt"
    ),
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Repository path (default: current directory)"
    ),
    config_file: str = typer.Option(
        "config/agents/platform_agent.toml",
        "--config",
        "-c",
        help="Agent configuration file"
    )
):
    """
    Platform Agent: TAP + TOML configuration for platform engineering.

    Platform engineering agent for automating development workflows:
    - TOML-based configuration (consistent with project standards)
    - TAP tools for AI autonomous decision-making
    - Framework-agnostic (pure TAP)
    - Extensible for Git, GitHub, CI/CD tasks

    The AI decides which tools to use:
    - get_git_status: Check repository status
    - analyze_git_diff: Understand what changed
    - create_commit: Create conventional commit

    Example:
        titan agent platform                # Interactive mode
        titan agent platform --yes          # Auto-confirm
        titan agent platform -p /path       # Custom repo path
        titan agent platform -c custom.toml # Custom config
    """
    text = TextRenderer()

    # Header
    text.title("🤖 Platform Agent (TAP + TOML)")
    text.line()
    text.info("Platform engineering agent with TOML configuration")
    text.line()

    # Initialize config
    config = TitanConfig()
    secrets = SecretManager()

    # Check AI configuration
    if not config.config.ai:
        text.error("❌ AI not configured. Run: titan ai configure")
        raise typer.Exit(1)

    # Build context with Git and AI
    try:
        context = (
            WorkflowContextBuilder(config=config, secrets=secrets)
            .with_git(repo_path=str(path))
            .with_ai()
            .with_ui()
            .build()
        )
    except Exception as e:
        text.error(f"❌ Failed to initialize: {e}")
        raise typer.Exit(1)

    # Set auto-confirm flag
    context.data["auto_confirm"] = auto_confirm

    # Load agent from TOML
    try:
        from ..agents.platform_agent import PlatformAgent

        agent = PlatformAgent.from_toml(config_file)

        text.info(f"📄 Loaded config: {config_file}")
        text.line()

    except FileNotFoundError as e:
        text.error(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)
    except Exception as e:
        text.error(f"❌ Failed to load agent: {e}")
        raise typer.Exit(1)

    # Run agent
    try:
        result = agent.run(context, user_context="")

        text.line()

        if result.success:
            text.success("✅ Agent completed successfully!")

            # Show metadata
            if result.metadata:
                provider = result.metadata.get("provider", "unknown")
                tools_used = result.metadata.get("tools_used", 0)

                text.line()
                text.info("📝 Execution Details:")
                text.body(f"Provider: {provider}", style="dim")
                text.body(f"Tools available: {tools_used}", style="dim")

        else:
            text.warning(f"⚠️  {result.message}")

    except KeyboardInterrupt:
        text.line()
        text.warning("⚠️  Cancelled by user")
        raise typer.Exit(0)
    except Exception as e:
        text.line()
        text.error(f"❌ Agent failed: {e}")
        raise typer.Exit(1)


@agent_app.command("auto-commit-lg")
@agent_app.command("commit-lg")  # Alias
def auto_commit_langgraph(
    auto_confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt"
    ),
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Repository path (default: current directory)"
    )
):
    """
    Auto-commit with LangGraph: AI agent with complex workflow support.

    This agent includes a LangGraph workflow as a TAP tool. The AI
    autonomously decides whether to use:
    - Simple tools (for straightforward commits)
    - Complex LangGraph workflow (for multi-module scenarios)

    The LangGraph workflow:
    - Analyzes all changed files
    - Groups changes by module
    - Creates multiple focused commits (one per module)

    Example:
        titan agent auto-commit-lg           # Interactive mode
        titan agent commit-lg --yes          # Auto-confirm
        titan agent commit-lg -p /path       # Custom repo path

    Note: Requires LangGraph: pip install langgraph langchain-core
    """
    text = TextRenderer()

    # Header
    text.title("🤖 Auto-Commit Agent (with LangGraph)")
    text.line()
    text.info("AI-powered commits with complex workflow support")
    text.line()

    # Initialize config
    config = TitanConfig()
    secrets = SecretManager()

    # Check AI configuration
    if not config.config.ai:
        text.error("❌ AI not configured. Run: titan ai configure")
        raise typer.Exit(1)

    # Build context with Git and AI
    try:
        context = (
            WorkflowContextBuilder(config=config, secrets=secrets)
            .with_git(repo_path=str(path))
            .with_ai()
            .with_ui()
            .build()
        )
    except Exception as e:
        text.error(f"❌ Failed to initialize: {e}")
        raise typer.Exit(1)

    # Set auto-confirm flag
    context.data["auto_confirm"] = auto_confirm

    # Import agent step (uses LangGraph)
    from ..agents.auto_commit_langgraph import auto_commit_langgraph_step

    # Create workflow
    workflow = BaseWorkflow(
        name="Auto-Commit (LangGraph)",
        steps=[auto_commit_langgraph_step]
    )

    # Run workflow
    try:
        result = workflow.run(context)

        text.line()

        if result.success:
            text.success("✅ Commit(s) created successfully!")

            # Show metadata
            if result.metadata:
                method = result.metadata.get("method", "unknown")
                tokens = result.metadata.get("tokens_used", 0)

                text.line()
                text.info("📝 Details:")

                # Show method used
                if method == "ai_tap_langgraph":
                    text.body("Method: AI + TAP + LangGraph workflow", style="bold cyan")
                    workflow_output = result.metadata.get("workflow_output", "")
                    if workflow_output:
                        text.line()
                        text.body(workflow_output)
                else:
                    text.body(f"Method: {method}", style="dim")

                    commit_msg = result.metadata.get("commit_message")
                    if commit_msg:
                        text.body(f"Message: {commit_msg}", style="dim")

                # Show tokens
                if tokens > 0:
                    text.body(f"Tokens used: ~{tokens}", style="dim")
                else:
                    text.body(f"Tokens used: 0 (no AI needed!)", style="bold green")

                tools_used = result.metadata.get("tools_used", [])
                if tools_used:
                    text.body(f"Tools used: {', '.join(tools_used)}", style="dim")

        else:
            text.warning(f"⚠️  {result.message}")

    except KeyboardInterrupt:
        text.line()
        text.warning("⚠️  Cancelled by user")
        raise typer.Exit(0)
    except Exception as e:
        text.line()
        text.error(f"❌ Workflow failed: {e}")
        raise typer.Exit(1)
