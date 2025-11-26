# commands/init.py
import typer
from pathlib import Path
from rich.prompt import Prompt
from ..core.plugin_registry import PluginRegistry
from ..ui.components.typography import TextRenderer

# Create a new Typer app for the 'init' command to live in
# This isn't strictly necessary for one command, but it's a good pattern
# if you plan to add more commands to this module.
init_app = typer.Typer(name="init", help="Initialize a new Titan project.")

def generate_config_template(project_name: str, installed_plugins: list[str]) -> str:
    """Generates the content for a default .titan/config.toml file."""
    
    config_lines = [
        '[project]',
        f'name = "{project_name}" ',
        'type = "generic"',
        '',
        '# --- AI Configuration (Optional) ---',
        '# [ai]',
        '# provider = "anthropic"  # anthropic, openai, gemini',
        '# model = "claude-3-haiku-20240307"',
        '',
        '# --- Plugin Configuration ---',
        '# Enable and configure plugins here.',
        '[plugins]',
    ]

    # Add discovered plugins, commented out by default
    for plugin in installed_plugins:
        config_lines.append(f'# [plugins.{plugin}]')
        config_lines.append(f'# enabled = true')
        config_lines.append('')
    
    return "\n".join(config_lines)


@init_app.callback(invoke_without_command=True)
def init():
    """
    Initialize Titan project in the current directory.
    
    This creates a .titan/config.toml file with a basic configuration
    and lists all discovered plugins for you to enable.
    """
    text = TextRenderer()
    
    text.title("🎛️ Titan CLI - Project Initialization")
    text.line()

    # Discover installed plugins
    registry = PluginRegistry()
    installed = registry.list_installed()

    # Ask for project name
    try:
        project_name = Prompt.ask("Enter a name for this project")
    except Exception:
        # In non-interactive environments, default to the current directory name
        project_name = Path.cwd().name

    # Create .titan directory
    titan_dir = Path.cwd() / ".titan"
    titan_dir.mkdir(exist_ok=True)

    # Generate config with installed plugins commented
    config_content = generate_config_template(
        project_name=project_name,
        installed_plugins=installed
    )

    config_path = titan_dir / "config.toml"
    config_path.write_text(config_content)

    text.success(f"Project initialized! Edit your configuration at: {config_path.relative_to(Path.cwd())}")
