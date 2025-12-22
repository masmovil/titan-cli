# titan_cli/commands/cli.py
import typer
from typing import Optional
from titan_cli.external_cli.helper import launch_cli_tool
from titan_cli.messages import msg

cli_app = typer.Typer(name="cli", help=msg.ExternalCLI.HELP_TEXT)

@cli_app.command("launch")
def launch_cli(
    cli_name: str = typer.Argument(..., help="The name of the CLI to launch (e.g., 'claude', 'gemini')."),
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for the CLI.")
):
    """
    Launch a generic CLI tool.
    """
    launch_cli_tool(cli_name, prompt)

@cli_app.command("claude")
def launch_claude(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for Claude Code.")
):
    """
    Launch Claude Code CLI.
    """
    launch_cli_tool("claude", prompt)

@cli_app.command("gemini")
def launch_gemini(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for Gemini CLI.")
):
    """
    Launch Gemini CLI.
    """
    launch_cli_tool("gemini", prompt)