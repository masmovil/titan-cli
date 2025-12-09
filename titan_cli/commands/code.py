# titan_cli/commands/code.py
import typer
from typing import Optional

from titan_cli.utils.claude_integration import ClaudeCodeLauncher
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg

code_app = typer.Typer(name="code", help=msg.Code.HELP_TEXT)

@code_app.callback(invoke_without_command=True)
def launch_code(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for Claude")
):
    """
    Launch Claude Code CLI from anywhere in Titan.
    
    Examples:
        titan code
        titan code "help me debug this workflow"
    """
    text = TextRenderer()

    if not ClaudeCodeLauncher.is_available():
        text.error(msg.Code.NOT_INSTALLED)
        text.body(msg.Code.INSTALL_INSTRUCTIONS)
        raise typer.Exit(1)

    text.info(msg.Code.LAUNCHING)
    if prompt:
        text.body(msg.Code.INITIAL_PROMPT.format(prompt=prompt))
    text.line()

    try:
        ClaudeCodeLauncher.launch(prompt=prompt)
    except KeyboardInterrupt:
        text.warning(msg.Code.INTERRUPTED)

    text.line()
    text.success(msg.Code.RETURNED)