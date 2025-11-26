# commands/init.py
import typer
import tomli
import tomli_w
from pathlib import Path
from rich.prompt import Prompt
from ..core.config import TitanConfig
from ..ui.components.typography import TextRenderer
from ..core.errors import ConfigWriteError
from ..messages import msg

# Create a new Typer app for the 'init' command to live in
init_app = typer.Typer(name="init", help="Initialize Titan's global configuration.")

@init_app.callback(invoke_without_command=True)
def init():
    """
    Initialize Titan's global configuration.
    
    This command helps you set up the global configuration, including the
    root directory where your projects are located.
    """
    text = TextRenderer()
    text.title("🎛️ Titan CLI - Global Setup")
    text.line()

    global_config_path = TitanConfig.GLOBAL_CONFIG
    global_config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing global config, if any
    config = {}
    if global_config_path.exists():
        with open(global_config_path, "rb") as f:
            try:
                config = tomli.load(f)
            except tomli.TOMLDecodeError:
                text.error(f"Could not parse existing global config at {global_config_path}. A new one will be created.")
                config = {}

    # Get current project root or prompt for it
    current_project_root = config.get("core", {}).get("project_root")
    
    text.info(f"The project root is the main folder where you store all your git repositories (e.g., ~/git, ~/Projects).")
    
    prompt_default = str(Path.home())
    if current_project_root:
        text.body(f"Current project root is: [primary]{current_project_root}[/primary]")
        prompt_default = current_project_root

    try:
        project_root_str = Prompt.ask(
            "Enter the path to your projects root directory",
            default=prompt_default
        )
        # Expand user path (e.g., ~) and resolve to an absolute path
        project_root = str(Path(project_root_str).expanduser().resolve())

        # Update the config dictionary
        config.setdefault("core", {})["project_root"] = project_root

        # Write the updated config back to the global file
        with open(global_config_path, "wb") as f:
            tomli_w.dump(config, f)

        text.success(f"Global configuration updated. Project root set to: {project_root}")

    except (EOFError, KeyboardInterrupt):
        # Handle non-interactive environment or user cancellation (Ctrl+C)
        text.warning(msg.Errors.OPERATION_CANCELLED_NO_CHANGES, show_emoji=False)
        raise typer.Exit(0)
    except (OSError, PermissionError) as e:
        error = ConfigWriteError(file_path=str(global_config_path), original_exception=e)
        text.error(str(error))
        raise typer.Exit(1)