# core/project_init.py
from pathlib import Path
import tomli_w

from ..ui.components.typography import TextRenderer
from ..ui.views.prompts import PromptsRenderer
from ..core.errors import ConfigWriteError
from ..core.plugins.plugin_registry import PluginRegistry
from ..messages import msg

def initialize_project(project_path: Path, registry: PluginRegistry) -> bool:
    """
    Interactively initializes a new Titan project in the specified directory.

    This function will prompt the user for project details (name, type)
    and create a .titan/config.toml file.

    Args:
        project_path: The absolute path to the project directory.
        registry: An instance of PluginRegistry to discover plugins.

    Returns:
        True if initialization was successful, False otherwise.
    """
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)
    titan_dir = project_path / ".titan"
    config_path = titan_dir / "config.toml"

    text.title(msg.Interactive.INIT_PROJECT_TITLE.format(project_name=project_path.name))
    text.line()

    try:
        # Prompt for Project Name
        project_name = prompts.ask_text(
            msg.Prompts.ENTER_NAME,
            default=project_path.name
        )

        # Prompt for Project Type
        project_type_choices = ["frontend", "backend", "fullstack", "library", "generic", "other"]
        project_type = prompts.ask_choice(
            msg.Prompts.SELECT_PROJECT_TYPE,
            choices=project_type_choices,
            default="generic"
        )
        if project_type == "other":
            project_type = prompts.ask_text(msg.Prompts.ENTER_CUSTOM_PROJECT_TYPE)

        # Discover plugins to set them as disabled by default
        discovered_plugins = registry.list_discovered()

        # Prepare config structure
        config_data = {
            "project": {
                "name": project_name,
                "type": project_type
            },
            "plugins": {
                plugin_name: {"enabled": False}
                for plugin_name in discovered_plugins
            }
        }

        # Create .titan directory and config file
        titan_dir.mkdir(parents=True, exist_ok=True)

        with open(config_path, "wb") as f:
            tomli_w.dump(config_data, f)

        text.success(msg.Projects.INIT_SUCCESS.format(project_name=project_name, config_path=config_path))
        return True

    except (EOFError, KeyboardInterrupt):
        text.warning(msg.Projects.INIT_CANCELLED)
        return False
    except (OSError, PermissionError) as e:
        error = ConfigWriteError(file_path=str(config_path), original_exception=e)
        text.error(str(error))
        return False
