# core/config.py
from pathlib import Path
from typing import Optional, List
import tomli
import tomli_w
from .models import TitanConfigModel
from .plugins.plugin_registry import PluginRegistry
from .workflows import WorkflowRegistry, ProjectStepSource
from .secrets import SecretManager
from .errors import ConfigParseError, ConfigWriteError
from ..messages import msg

class TitanConfig:
    """Manages Titan configuration with global + project merge"""

    GLOBAL_CONFIG = Path.home() / ".titan" / "config.toml"

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        global_config_path: Optional[Path] = None
    ):
        # Core dependencies
        self.registry = registry or PluginRegistry()

        # These are initialized in load() after config is read
        self.secrets = None  # Set by load()
        self._project_root = None  # Set by load()
        self._active_project_path = None  # Set by load()
        self._workflow_registry = None  # Set by load()
        self._plugin_warnings = []

        # Use custom global config path if provided (for testing), otherwise use default
        self._global_config_path = global_config_path or self.GLOBAL_CONFIG

        # Initial load
        self.load()

    def load(self):
        """
        Reloads the entire configuration from disk, including global config
        and the config for the currently active project.
        """
        had_invalid_active_project = False
        # Load global config first to find project_root and active_project
        self.global_config = self._load_toml(self._global_config_path)
        
        # Temporarily validate global to access core settings
        temp_global_model = TitanConfigModel(**self.global_config)
        
        active_project_name = None
        project_root_str = None
        
        if temp_global_model.core:
            project_root_str = temp_global_model.core.project_root
            active_project_name = temp_global_model.core.active_project

        # Set project_root
        if project_root_str:
            self._project_root = Path(project_root_str)
        else:
            self._project_root = Path.cwd()

        # Determine the project config path
        self.project_config_path = None
        if active_project_name:
            active_project_path = self._project_root / active_project_name
            # An active project must have its config file directly within its path.
            # We don't search up the tree, because that could incorrectly find a parent
            # project's config or the global config.
            expected_config_path = active_project_path / ".titan" / "config.toml"

            if expected_config_path.is_file():
                self.project_config_path = expected_config_path
                self._active_project_path = active_project_path
            else:
                # The configured active project is invalid. Unset it.
                if 'core' in self.global_config and 'active_project' in self.global_config['core']:
                    del self.global_config['core']['active_project']
                active_project_name = None
                self._active_project_path = None
                had_invalid_active_project = True
        else:
            self._active_project_path = None

        # Load project config
        self.project_config = self._load_toml(self.project_config_path)

        # Merge and validate final config
        merged = self._merge_configs(self.global_config, self.project_config)
        self.config = TitanConfigModel(**merged)

        # Re-initialize dependencies that depend on the final config
        # Use active_project_path for secrets if available, otherwise project_root
        secrets_path = self._active_project_path if self._active_project_path and self._active_project_path.is_dir() else self._project_root
        self.secrets = SecretManager(project_path=secrets_path if secrets_path and secrets_path.is_dir() else None)
        
        # Reset and re-initialize plugins
        self.registry.reset()
        self.registry.initialize_plugins(config=self, secrets=self.secrets)
        self._plugin_warnings = self.registry.list_failed()

        # Re-initialize WorkflowRegistry
        # Use active_project_path for workflows if available, otherwise project_root
        workflow_path = self._active_project_path if self._active_project_path else self._project_root
        project_step_source = ProjectStepSource(project_root=workflow_path)
        self._workflow_registry = WorkflowRegistry(
            project_root=workflow_path,
            plugin_registry=self.registry,
            project_step_source=project_step_source
        )

        if had_invalid_active_project:
            try:
                self._save_global_config()
            except ConfigWriteError as e:
                import warnings
                warnings.warn(msg.Config.SAVE_GLOBAL_CONFIG_FAILED_UNSET.format(e=e), RuntimeWarning)
            
            # Store warning to show later
            import warnings
            warnings.warn(
                msg.Config.ACTIVE_PROJECT_INVALID.format(project_name=active_project_name),
                RuntimeWarning
            )


    def _find_project_config(self, start_path: Optional[Path] = None) -> Optional[Path]:
        """Search for .titan/config.toml up the directory tree"""
        current = (start_path or Path.cwd()).resolve()

        # In a test environment, Path.cwd() might not be under /home/
        # and we need a stopping condition.
        sentinel = Path(current.root)
        
        while current != current.parent and current != sentinel:
            config_path = current / ".titan" / "config.toml"
            if config_path.exists():
                return config_path
            current = current.parent

        return None

    def _load_toml(self, path: Optional[Path]) -> dict:
        """Load TOML file, returning an empty dict on failure."""
        if not path or not path.exists():
            return {}

        with open(path, "rb") as f:
            try:
                return tomli.load(f)
            except tomli.TOMLDecodeError as e:
                # Wrap the generic exception. Warnings will be handled by CLI commands.
                _ = ConfigParseError(file_path=str(path), original_exception=e)
                return {}

    def _merge_configs(self, global_cfg: dict, project_cfg: dict) -> dict:
        """Merge global and project configs (project overrides global)"""
        merged = {**global_cfg}

        # Project config overrides global
        for key, value in project_cfg.items():
            if key == "plugins" and isinstance(value, dict):
                merged_plugins = merged.setdefault("plugins", {})

                for plugin_name, plugin_data_project in value.items():
                    plugin_data_global = merged_plugins.get(plugin_name, {})

                    # Start with a copy of the global plugin config for this specific plugin
                    # This ensures all global settings (like 'enabled') are carried over
                    # unless explicitly overridden.
                    final_plugin_data = {**plugin_data_global}

                    # Merge top-level keys from project config, excluding 'config'
                    for pk, pv in plugin_data_project.items():
                        if pk != "config":
                            final_plugin_data[pk] = pv

                    # Handle the nested 'config' dictionary separately (deep merge)
                    config_section_global = plugin_data_global.get("config", {})
                    config_section_project = plugin_data_project.get("config", {})

                    if config_section_global or config_section_project:
                        final_plugin_data["config"] = {**config_section_global, **config_section_project}
                    elif "config" in final_plugin_data: # If global had a config, and project didn't touch it
                         pass # Keep the global config

                    merged_plugins[plugin_name] = final_plugin_data
            elif key == "ai" and isinstance(value, dict):
                # AI config should be merged intelligently (global + project)
                # Global AI config is always available, project can override specific settings
                merged_ai = merged.setdefault("ai", {})

                # Merge providers (project providers supplement global providers)
                if "providers" in value:
                    merged_providers = merged_ai.setdefault("providers", {})
                    # Deep merge: preserve global fields, override with project fields
                    for provider_id, provider_data in value["providers"].items():
                        if provider_id in merged_providers:
                            # Provider exists in global: deep merge (extend, not replace)
                            merged_providers[provider_id] = {**merged_providers[provider_id], **provider_data}
                        else:
                            # New provider: just add it
                            merged_providers[provider_id] = provider_data

                # Project can override default provider, otherwise keep global
                if "default" in value:
                    merged_ai["default"] = value["default"]

                # Merge any other AI settings
                for ai_key, ai_value in value.items():
                    if ai_key not in ("providers", "default"):
                        merged_ai[ai_key] = ai_value
            else:
                merged[key] = value

        return merged

    @property
    def project_root(self) -> Path:
        """Return the resolved project root path."""
        return self._project_root

    @property
    def active_project_path(self) -> Optional[Path]:
        """Return the path to the currently active project."""
        return self._active_project_path

    @property
    def workflows(self) -> WorkflowRegistry:
        """Access to workflow registry."""
        return self._workflow_registry

    def get_project_root(self) -> Optional[str]:
        """Returns the configured project root, or None if not set."""
        if self.config and self.config.core and self.config.core.project_root:
            return self.config.core.project_root
        return None

    def get_enabled_plugins(self) -> List[str]:
        """Get list of enabled plugins"""
        if not self.config or not self.config.plugins:
            return []
        return [
            name for name, plugin_cfg in self.config.plugins.items()
            if plugin_cfg.enabled
        ]

    def get_plugin_warnings(self) -> List[str]:
        """Get list of failed or misconfigured plugins."""
        return self._plugin_warnings

    def get_active_project(self) -> Optional[str]:
        """Get currently active project name from global config."""
        if self.config and self.config.core and self.config.core.active_project:
            return self.config.core.active_project
        return None

    def set_active_project(self, project_name: str):
        """Set active project and save to global config."""
        if self.config.core:
            self.config.core.active_project = project_name
            self._save_global_config()
        # If core config doesn't exist, we might need to create it
        # For now, we assume it exists if we are setting an active project.

    def get_active_project_path(self) -> Optional[Path]:
        """Get path to active project."""
        active_project_name = self.get_active_project()
        project_root_str = self.get_project_root()

        if not active_project_name or not project_root_str:
            return None

        return Path(project_root_str) / active_project_name

    def _save_global_config(self):
        """Saves the current state of the global config to disk."""
        if not self._global_config_path.parent.exists():
            try:
                self._global_config_path.parent.mkdir(parents=True)
            except OSError as e:
                raise ConfigWriteError(file_path=str(self._global_config_path), original_exception=e)

        existing_global_config = {}
        if self._global_config_path.exists():
            try:
                with open(self._global_config_path, "rb") as f:
                    import tomllib
                    existing_global_config = tomllib.load(f)
            except Exception:
                pass

        config_to_save = self.config.model_dump(exclude_none=True)

        if 'core' in config_to_save:
            existing_global_config['core'] = config_to_save['core']

        try:
            with open(self._global_config_path, "wb") as f:
                import tomli_w
                tomli_w.dump(existing_global_config, f)
        except ImportError as e:
            raise ConfigWriteError(file_path=str(self._global_config_path), original_exception=e)
        except Exception as e:
            raise ConfigWriteError(file_path=str(self._global_config_path), original_exception=e)

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if plugin is enabled"""
        if not self.config or not self.config.plugins:
            return False
        plugin_cfg = self.config.plugins.get(plugin_name)
        return plugin_cfg.enabled if plugin_cfg else False

