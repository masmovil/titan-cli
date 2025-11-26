# core/config.py
from pathlib import Path
from typing import Optional, List, Dict
import tomli
from .models import TitanConfigModel
from .plugin_registry import PluginRegistry

class TitanConfig:
    """Manages Titan configuration with global + project merge"""

    GLOBAL_CONFIG = Path.home() / ".titan" / "config.toml"

    def __init__(self, project_path: Optional[Path] = None):
        # Plugin discovery
        self.registry = PluginRegistry()

        # Load configs
        self.global_config = self._load_toml(self.GLOBAL_CONFIG)
        self.project_config_path = self._find_project_config(project_path)
        self.project_config = self._load_toml(self.project_config_path)

        # Merge
        merged = self._merge_configs(self.global_config, self.project_config)

        # Validate with Pydantic
        self.config = TitanConfigModel(**merged)

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
        """Load TOML file"""
        if not path or not path.exists():
            return {}

        with open(path, "rb") as f:
            try:
                return tomli.load(f)
            except tomli.TOMLDecodeError:
                # In a real app, you'd use a proper logger here
                print(f"Warning: Could not decode TOML file at {path}")
                return {}

    def _merge_configs(self, global_cfg: dict, project_cfg: dict) -> dict:
        """Merge global and project configs (project overrides global)"""
        merged = {**global_cfg}

        # Project config overrides global
        for key, value in project_cfg.items():
            if key == "plugins" and isinstance(value, dict) and isinstance(merged.get("plugins"), dict):
                # Merge plugins separately
                merged.setdefault("plugins", {}).update(value)
            else:
                merged[key] = value

        return merged

    def get_enabled_plugins(self) -> List[str]:
        """Get list of enabled plugins"""
        if not self.config or not self.config.plugins:
            return []
        return [
            name for name, plugin_cfg in self.config.plugins.items()
            if plugin_cfg.enabled
        ]

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if plugin is enabled"""
        if not self.config or not self.config.plugins:
            return False
        plugin_cfg = self.config.plugins.get(plugin_name)
        return plugin_cfg.enabled if plugin_cfg else False
