# titan_cli/external_cli/helper.py
import typer
from typing import Optional
from titan_cli.external_cli.launcher import CLILauncher
from titan_cli.external_cli.configs import CLI_REGISTRY
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg

def launch_cli_tool(cli_name: str, prompt: Optional[str] = None):
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
