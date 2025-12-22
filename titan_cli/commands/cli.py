# titan_cli/commands/cli.py
import typer
from typing import Optional
from titan_cli.utils.cli_launcher import CLILauncher
from titan_cli.utils.cli_configs import CLI_REGISTRY
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg

cli_app = typer.Typer(name="cli", help=msg.ExternalCLI.HELP_TEXT)

def _launch_cli(cli_name: str, prompt: Optional[str] = None):
    """Generic function to launch a CLI tool using the registry."""
    text = TextRenderer()
    
    config = CLI_REGISTRY.get(cli_name)
    if not config:
        text.error(f"Unknown CLI: {cli_name}")
        raise typer.Exit(1)

    display_name = config.get("display_name", cli_name)
    launcher = CLILauncher(
        cli_name=cli_name,
        install_instructions=config.get("install_instructions"),
        prompt_flag=config.get("prompt_flag")
    )

    if not launcher.is_available():
        text.error(msg.ExternalCLI.NOT_INSTALLED.format(cli_name=display_name))
        if launcher.install_instructions:
            text.body(launcher.install_instructions)
        else:
            text.body(msg.ExternalCLI.INSTALL_INSTRUCTIONS.format(cli_name=display_name))
        raise typer.Exit(1)

    text.info(msg.ExternalCLI.LAUNCHING.format(cli_name=display_name))
    if prompt:
        text.body(msg.ExternalCLI.INITIAL_PROMPT.format(prompt=prompt))
    text.line()

    try:
        launcher.launch(prompt=prompt)
    except KeyboardInterrupt:
        text.warning(msg.ExternalCLI.INTERRUPTED.format(cli_name=display_name))

    text.line()
    text.success(msg.ExternalCLI.RETURNED)

@cli_app.command("launch")
def launch_cli(
    cli_name: str = typer.Argument(..., help="The name of the CLI to launch (e.g., 'claude', 'gemini')."),
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for the CLI.")
):
    """
    Launch a generic CLI tool.
    """
    _launch_cli(cli_name, prompt)

@cli_app.command("claude")
def launch_claude(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for Claude Code.")
):
    """
    Launch Claude Code CLI.
    """
    _launch_cli("claude", prompt)

@cli_app.command("gemini")
def launch_gemini(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for Gemini CLI.")
):
    """
    Launch Gemini CLI.
    """
    _launch_cli("gemini", prompt)