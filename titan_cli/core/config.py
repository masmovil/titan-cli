# core/config.py
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import List, Optional
import tomli
from .models import AIConfig, AIPreferences, TitanConfigModel
from .migrations import MigrationManager
from .plugins.plugin_registry import PluginRegistry
from .workflows import WorkflowRegistry, ProjectStepSource, UserStepSource
from .secrets import SecretManager
from .errors import ConfigParseError, ConfigWriteError
from .utils import find_project_root
from .logging import get_logger
from .plugins.community_sources import PluginChannel

logger = get_logger(__name__)

class TitanConfig:
    """Manages Titan configuration with global + project merge"""

    GLOBAL_CONFIG = Path.home() / ".titan" / "config.toml"
    global_migration_manager = MigrationManager()
    project_migration_manager = MigrationManager()

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        global_config_path: Optional[Path] = None,
        skip_plugin_init: bool = False
    ):
        # Core dependencies
        self.registry = registry or PluginRegistry()

        # These are initialized in load() after config is read
        self.secrets = None  # Set by load()
        self._project_root = None  # Set by load()
        self._active_project_path = None  # Set by load()
        self._workflow_registry = None  # Set by load()
        self._plugin_warnings = []
        self._plugin_sync_events = []

        # Use custom global config path if provided (for testing), otherwise use default
        self._global_config_path = global_config_path or self.GLOBAL_CONFIG

        # Initial load
        self.load(skip_plugin_init=skip_plugin_init)

    def load(self, skip_plugin_init: bool = False):
        """
        Reloads the entire configuration from disk, including global config
        and the project config from the current working directory.

        Args:
            skip_plugin_init: If True, skip plugin initialization. Useful during setup wizards.
        """
        # Load global config
        self.global_config = self._load_and_migrate_toml(
            self._global_config_path,
            migration_manager=self.global_migration_manager,
        )

        # Set project root: git root if inside a repo, otherwise cwd
        project_root = find_project_root()
        self._project_root = project_root
        self._active_project_path = project_root
        logger.debug("project_root_resolved", path=str(project_root))

        # Look for project config starting from project root
        self.project_config_path = self._find_project_config(project_root)

        # Load project config if it exists
        self.project_config = self._load_toml(self.project_config_path)

        # Merge and validate final config
        merged = self._merge_configs(self.global_config, self.project_config)
        self.config = TitanConfigModel(**merged)

        # Re-initialize dependencies that depend on the final config
        # Use project root for secrets
        self.secrets = SecretManager(project_path=project_root if project_root.is_dir() else None)

        # Reset and re-initialize plugins (unless skipped during setup)
        if not skip_plugin_init:
            self.registry.reset()
            self.registry.initialize_plugins(config=self, secrets=self.secrets)
            self._plugin_warnings = self.registry.list_failed()
            self._plugin_sync_events = self.registry.list_sync_events()

        # Re-initialize WorkflowRegistry using project root
        project_step_source = ProjectStepSource(project_root=project_root)
        user_step_source = UserStepSource()
        self._workflow_registry = WorkflowRegistry(
            project_root=project_root,
            plugin_registry=self.registry,
            project_step_source=project_step_source,
            user_step_source=user_step_source,
            config=self
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

    def _load_and_migrate_toml(
        self,
        path: Optional[Path],
        migration_manager: MigrationManager,
        write_on_migration: bool = True,
    ) -> dict:
        """Load TOML and normalize it to the current config schema."""
        raw_config = self._load_toml(path)
        if not raw_config:
            return {}

        migration_result = migration_manager.migrate(raw_config)
        if migration_result.changed:
            logger.info(
                "config_migrated",
                path=str(path),
                from_version=migration_result.original_version,
                to_version=migration_result.final_version,
                steps=migration_result.applied_steps,
            )
            if write_on_migration and path is not None:
                self._write_toml(path, migration_result.data)

        return migration_result.data

    def _merge_configs(self, global_cfg: dict, project_cfg: dict) -> dict:
        """Merge global and project configs (project overrides global)"""
        merged = deepcopy(global_cfg)

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

                # Merge connections (project connections supplement global connections)
                if "connections" in value:
                    merged_connections = merged_ai.setdefault("connections", {})
                    # Deep merge: preserve global fields, override with project fields
                    for connection_id, connection_data in value["connections"].items():
                        if connection_id in merged_connections:
                            # Connection exists in global: deep merge (extend, not replace)
                            merged_connections[connection_id] = {
                                **merged_connections[connection_id],
                                **connection_data,
                            }
                        else:
                            # New connection: just add it
                            merged_connections[connection_id] = connection_data

                # Project can override default connection, otherwise keep global
                if "default_connection" in value:
                    merged_ai["default_connection"] = value["default_connection"]

                # Merge any other AI settings
                for ai_key, ai_value in value.items():
                    if ai_key not in ("connections", "default_connection"):
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


    def get_enabled_plugins(self) -> List[str]:
        """Get list of enabled plugins"""
        if not self.config or not self.config.plugins:
            return []
        return [
            name for name, plugin_cfg in self.config.plugins.items()
            if self.is_plugin_enabled(name)
        ]

    def get_plugin_warnings(self) -> List[str]:
        """Get list of failed or misconfigured plugins."""
        return self._plugin_warnings

    def get_plugin_sync_events(self) -> List[str]:
        """Get list of plugin auto-sync events from the latest load cycle."""
        return self._plugin_sync_events

    def get_project_name(self) -> Optional[str]:
        """Get the current project name from project config."""
        if self.config and self.config.project:
            return self.config.project.name
        return None

    def _save_global_config(self):
        """Saves the current state of the global config to disk."""
        existing_global_config = {}
        if self._global_config_path.exists():
            try:
                with open(self._global_config_path, "rb") as f:
                    import tomllib
                    existing_global_config = tomllib.load(f)
            except Exception:
                pass

        # Save only AI configuration to global config
        # Project-specific settings are stored in project's .titan/config.toml
        config_to_save = self.config.model_dump(exclude_none=True)
        existing_global_config["config_version"] = self.config.config_version

        if 'ai' in config_to_save:
            existing_global_config['ai'] = config_to_save['ai']

        self._write_global_config(existing_global_config)

    def get_ai_connections_config(self) -> dict:
        """Return global AI config normalized to the current schema."""
        config_data = self._load_and_migrate_toml(
            self._global_config_path,
            migration_manager=self.global_migration_manager,
        )
        ai_cfg = config_data.setdefault("ai", {})
        ai_cfg.setdefault("connections", {})
        ai_cfg.setdefault("default_connection", None)
        return ai_cfg

    def save_ai_connections_config(self, ai_config: dict) -> None:
        """Persist global AI config in the current schema version."""
        config_data = self._load_and_migrate_toml(
            self._global_config_path,
            migration_manager=self.global_migration_manager,
        )
        config_data["config_version"] = (
            self.config.config_version if getattr(self, "config", None) else "1.0"
        )
        config_data["ai"] = ai_config
        self._write_global_config(config_data)

    def upsert_ai_connection(self, connection_id: str, connection_data: dict) -> None:
        """Create or update a single AI connection."""
        ai_cfg = self.get_ai_connections_config()
        ai_cfg.setdefault("connections", {})
        ai_cfg["connections"][connection_id] = connection_data

        if not ai_cfg.get("default_connection"):
            ai_cfg["default_connection"] = connection_id

        self.save_ai_connections_config(ai_cfg)

    def update_ai_connection(self, connection_id: str, updates: dict) -> None:
        """Update fields of an existing AI connection."""
        ai_cfg = self.get_ai_connections_config()
        connections = ai_cfg.get("connections", {})

        if connection_id not in connections:
            raise ValueError(f"AI connection '{connection_id}' not found.")

        connections[connection_id] = {
            **connections[connection_id],
            **updates,
        }
        self.save_ai_connections_config(ai_cfg)

    def set_default_ai_connection(self, connection_id: str) -> None:
        """Set the global default AI connection."""
        ai_cfg = self.get_ai_connections_config()
        if connection_id not in ai_cfg.get("connections", {}):
            raise ValueError(f"AI connection '{connection_id}' not found.")
        ai_cfg["default_connection"] = connection_id
        self.save_ai_connections_config(ai_cfg)

    def delete_ai_connection(self, connection_id: str) -> None:
        """Delete an AI connection and repair the default pointer if needed."""
        ai_cfg = self.get_ai_connections_config()
        connections = ai_cfg.get("connections", {})
        if connection_id not in connections:
            return

        del connections[connection_id]

        if ai_cfg.get("default_connection") == connection_id:
            ai_cfg["default_connection"] = next(iter(connections), None)

        self.save_ai_connections_config(ai_cfg)

    def get_ai_preferences_config(self) -> dict:
        """Return global AI preferences: one provider choice per AI task."""
        config_data = self._load_and_migrate_toml(
            self._global_config_path,
            migration_manager=self.global_migration_manager,
        )
        ai_cfg = config_data.setdefault("ai", {})
        prefs = ai_cfg.setdefault("preferences", {})
        prefs.setdefault("tasks", {})
        return prefs

    def save_ai_preferences_config(self, preferences: dict) -> None:
        """Persist global AI preferences without touching AI connections."""
        config_data = self._load_and_migrate_toml(
            self._global_config_path,
            migration_manager=self.global_migration_manager,
        )
        config_data["config_version"] = (
            self.config.config_version if getattr(self, "config", None) else "1.0"
        )
        config_data.setdefault("ai", {})["preferences"] = preferences
        self._write_global_config(config_data)
        self._sync_in_memory_ai_preferences(preferences)

    def _sync_in_memory_ai_preferences(self, preferences: dict) -> None:
        """
        Keep the already-parsed `self.config.ai.preferences` in sync with what
        was just persisted to disk, so a caller holding this same TitanConfig
        instance (e.g. a workflow step, in the same process) sees the new
        preference immediately, without needing a full `.load()`.
        """
        if not getattr(self, "config", None):
            return
        parsed = AIPreferences(**preferences)
        if self.config.ai:
            self.config.ai.preferences = parsed
        else:
            self.config.ai = AIConfig(preferences=parsed)

    def upsert_task_ai_preference(self, task: str, preference_data: dict) -> None:
        """Create or update a persisted preference for an AI task."""
        prefs = self.get_ai_preferences_config()
        prefs["tasks"][task] = self._strip_none(preference_data)
        self.save_ai_preferences_config(prefs)

    @staticmethod
    def _strip_none(data: dict) -> dict:
        """Drop None-valued keys - TOML has no null type."""
        return {k: v for k, v in data.items() if v is not None}

    def delete_task_ai_preference(self, task: str) -> None:
        """Delete a persisted task-level AI preference, if present."""
        prefs = self.get_ai_preferences_config()
        if task in prefs["tasks"]:
            del prefs["tasks"][task]
            self.save_ai_preferences_config(prefs)

    def _write_toml(self, path: Path, data: dict) -> None:
        """Write raw TOML data to disk."""
        if not path.parent.exists():
            try:
                path.parent.mkdir(parents=True)
            except OSError as e:
                raise ConfigWriteError(file_path=str(path), original_exception=e)

        try:
            with open(path, "wb") as f:
                import tomli_w
                tomli_w.dump(data, f)
        except ImportError as e:
            raise ConfigWriteError(file_path=str(path), original_exception=e)
        except Exception as e:
            raise ConfigWriteError(file_path=str(path), original_exception=e)

    def _write_global_config(self, data: dict) -> None:
        """Write raw global config data to disk."""
        self._write_toml(self._global_config_path, data)

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is effectively enabled for the current project.

        This is the source of truth for plugin activation. Do not infer enabled
        state from the merged plugin model alone, because global plugin metadata
        may exist without the plugin being explicitly enabled in the current
        project's config.
        """
        if not self.config or not self.config.plugins:
            return False
        project_plugins = self.project_config.get("plugins", {}) if self.project_config else {}
        if plugin_name not in project_plugins:
            return False

        # Slack is repo-scoped: it is only considered enabled when the current
        # project explicitly contains a complete Slack config block.
        if plugin_name == "slack":
            project_plugin_cfg = project_plugins.get(plugin_name, {})
            project_plugin_config = project_plugin_cfg.get("config", {})
            required_keys = {
                "oauth_client_id",
                "default_team_id",
                "default_team_name",
                "granted_scopes",
            }
            if not project_plugin_config or not required_keys.issubset(project_plugin_config):
                return False

        plugin_cfg = self.config.plugins.get(plugin_name)
        return plugin_cfg.enabled if plugin_cfg else False

    def get_plugin_source_channel(self, plugin_name: str) -> str:
        """Return the effective source channel for a plugin."""
        source = self.get_effective_plugin_source(plugin_name)
        return source.get("channel", PluginChannel.STABLE)

    def get_plugin_source_path(self, plugin_name: str) -> Optional[Path]:
        """Return the effective dev_local path for a plugin, if any."""
        source = self.get_effective_plugin_source(plugin_name)
        path = source.get("path")
        if not path:
            return None
        return Path(path).expanduser().resolve()

    def get_global_plugin_source(self, plugin_name: str) -> dict:
        """Return the raw user-local source override for a plugin in the active project."""
        scoped_source = self._get_project_source_scope_data().get("plugins", {}).get(plugin_name, {}).get("source", {})
        if scoped_source:
            return scoped_source.copy()

        # Backward-compatible fallback for older global config layouts.
        return (
            self.global_config.get("plugins", {})
            .get(plugin_name, {})
            .get("source", {})
            .copy()
        )

    def get_project_plugin_source(self, plugin_name: str) -> dict:
        """Return the raw project source definition for a plugin."""
        return (
            self.project_config.get("plugins", {})
            .get(plugin_name, {})
            .get("source", {})
            .copy()
        )

    def get_effective_plugin_source(self, plugin_name: str) -> dict:
        """Return the effective plugin source after applying local overrides."""
        global_source = self.get_global_plugin_source(plugin_name)
        project_source = self.get_project_plugin_source(plugin_name)

        if global_source.get("channel") == PluginChannel.DEV_LOCAL and global_source.get("path"):
            return {
                "channel": PluginChannel.DEV_LOCAL,
                "path": global_source.get("path"),
                "repo_url": project_source.get("repo_url"),
                "requested_ref": project_source.get("requested_ref"),
                "resolved_commit": project_source.get("resolved_commit"),
            }

        effective = dict(project_source)
        effective.setdefault("channel", PluginChannel.STABLE)

        # Preserve the remembered dev path for quick switching, but only as UX state.
        if global_source.get("path") and "path" not in effective:
            effective["path"] = global_source.get("path")

        return effective

    def get_project_plugin_repo_url(self, plugin_name: str) -> Optional[str]:
        """Return the shared stable repository URL for a plugin."""
        return self.get_project_plugin_source(plugin_name).get("repo_url")

    def get_project_plugin_requested_ref(self, plugin_name: str) -> Optional[str]:
        """Return the shared requested stable ref for a plugin."""
        return self.get_project_plugin_source(plugin_name).get("requested_ref")

    def get_project_plugin_resolved_commit(self, plugin_name: str) -> Optional[str]:
        """Return the shared resolved stable commit for a plugin."""
        return self.get_project_plugin_source(plugin_name).get("resolved_commit")

    def set_global_plugin_source(
        self,
        plugin_name: str,
        channel: str,
        path: Optional[str] = None,
    ) -> None:
        """Persist a plugin source override in the global user config."""
        config_data = self._load_toml(self._global_config_path)
        project_sources = config_data.setdefault("project_sources", {})
        project_table = project_sources.setdefault(self._get_project_source_scope_key(), {})
        project_table["project_path"] = str((self._project_root or Path.cwd()).resolve())
        plugins_table = project_table.setdefault("plugins", {})
        plugin_table = plugins_table.setdefault(plugin_name, {})
        source_table = plugin_table.setdefault("source", {})

        source_table["channel"] = channel
        if path:
            source_table["path"] = path
        else:
            source_table.pop("path", None)

        self._write_global_config(config_data)

    def clear_global_plugin_source(self, plugin_name: str) -> None:
        """Remove a plugin source override from the global user config."""
        config_data = self._load_toml(self._global_config_path)
        project_sources = config_data.get("project_sources", {})
        project_key = self._find_project_source_scope_key(project_sources)
        project_table = project_sources.get(project_key, {}) if project_key else {}
        plugins_table = project_table.get("plugins", {})
        plugin_table = plugins_table.get(plugin_name)
        if not plugin_table:
            # Fall back to cleaning any legacy global override for the plugin.
            legacy_plugins = config_data.get("plugins", {})
            legacy_plugin = legacy_plugins.get(plugin_name)
            if not legacy_plugin:
                return
            legacy_plugin.pop("source", None)
            if not legacy_plugin:
                legacy_plugins.pop(plugin_name, None)
            if not legacy_plugins and "plugins" in config_data:
                config_data.pop("plugins", None)
            self._write_global_config(config_data)
            return

        plugin_table.pop("source", None)
        if not plugin_table:
            plugins_table.pop(plugin_name, None)
        if not plugins_table and "plugins" in project_table:
            project_table.pop("plugins", None)
        if self._project_source_table_empty(project_table) and project_key in project_sources:
            project_sources.pop(project_key, None)
        if not project_sources and "project_sources" in config_data:
            config_data.pop("project_sources", None)

        self._write_global_config(config_data)

    def _get_project_source_scope_key(self) -> str:
        """Return the global-config key used to scope local plugin overrides per project."""
        project_path = str((self._project_root or Path.cwd()).resolve())
        project_name = (self._project_root or Path.cwd()).resolve().name or "project"
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", project_name).strip("_").lower() or "project"
        digest = hashlib.sha256(project_path.encode("utf-8")).hexdigest()[:8]
        return f"p_{safe_name}_{digest}"

    def _get_project_source_scope_data(self) -> dict:
        """Return the scoped project source block for the active project."""
        project_sources = self.global_config.get("project_sources", {})
        project_key = self._find_project_source_scope_key(project_sources)
        if project_key:
            return project_sources.get(project_key, {})
        return {}

    def _find_project_source_scope_key(self, project_sources: dict) -> Optional[str]:
        """Find the project_sources key matching the active project."""
        current_path = str((self._project_root or Path.cwd()).resolve())
        preferred_key = self._get_project_source_scope_key()
        preferred_table = project_sources.get(preferred_key)
        if isinstance(preferred_table, dict):
            stored_path = preferred_table.get("project_path")
            if not stored_path or stored_path == current_path:
                return preferred_key

        for key, value in project_sources.items():
            if key == current_path:
                return key
            if isinstance(value, dict) and value.get("project_path") == current_path:
                return key
        return None

    def _project_source_table_empty(self, project_table: dict) -> bool:
        """Return whether a scoped project source block contains meaningful data."""
        return not any(key != "project_path" for key in project_table)

    def get_status_bar_info(self) -> dict:
        """
        Get information for the status bar display.

        Returns:
            A dict with keys: 'ai_info', 'project_name'
            Values are strings or None if not available.
        """
        # Extract AI info
        ai_info = None
        if self.config and self.config.ai:
            ai_config = self.config.ai
            default_connection_id = ai_config.default_connection

            if (
                default_connection_id
                and default_connection_id in ai_config.connections
            ):
                connection_config = ai_config.connections[default_connection_id]
                provider_name = (
                    connection_config.provider or connection_config.gateway_backend
                )
                model = connection_config.default_model or "default"
                ai_info = f"{provider_name}/{model}"

        # Extract project name from project config
        project_name = self.get_project_name()

        return {
            'ai_info': ai_info,
            'project_name': project_name
        }
