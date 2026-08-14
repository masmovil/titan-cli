"""
Base interface for Titan plugins.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from pathlib import Path


class TitanPlugin(ABC):
    """
    Base class for all Titan plugins.
    
    Plugins extend Titan CLI with:
    - Service clients (Git, GitHub, Jira, etc.)
    - Workflow steps (atomic operations)
    
    Example:
        class GitPlugin(TitanPlugin):
            @property
            def name(self) -> str:
                return "git"
            
            def get_client(self):
                return GitClient()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Plugin unique identifier.
        
        Returns:
            Plugin name (e.g., "git", "github", "jira")
        """
        pass

    @property
    def version(self) -> str:
        """Plugin version (default: "0.0.0")"""
        return "0.0.0"

    @property
    def description(self) -> str:
        """Plugin description (default: empty)"""
        return ""

    @property
    def dependencies(self) -> list[str]:
        """
        Other plugins this plugin depends on.
        
        Returns:
            List of plugin names (e.g., ["git"] for GitHub plugin)
        """
        return []

    def initialize(self, config: Any, broker: Any) -> None:
        """
        Initialize plugin with configuration and its scoped secret broker.

        Called once when plugin is loaded by PluginRegistry.

        Args:
            config: TitanConfig instance
            broker: SecretBroker scoped to this plugin's namespace. It can
                store/check/delete secrets and build authenticated clients,
                but never read a value back.
        """
        pass

    def get_client(self) -> Optional[Any]:
        """
        Get the main client instance for this plugin.
        
        This client will be injected into WorkflowContext.
        
        Returns:
            Client instance or None
        """
        return None

    def get_workflow_managers(self, project_root: Optional[Path] = None) -> Optional[Any]:
        """
        Get workflow-local managers for this plugin.

        Managers are non-client dependencies used by workflow steps, such as
        local config resolvers, registries, or loaders.

        Args:
            project_root: Current project root when available.

        Returns:
            Plugin-specific managers container or None
        """
        return None

    def has_custom_config_screen(self) -> bool:
        """Return whether this plugin provides a custom configuration screen."""
        return False

    def create_config_screen(self, config: Any) -> Optional[Any]:
        """Create a plugin-specific configuration screen when supported."""
        return None

    def get_steps(self) -> Dict[str, Callable]:
        """
        Get workflow steps provided by this plugin.
        
        Returns:
            Dict mapping step name to step function
        """
        return {}

    def is_available(self) -> bool:
        """
        Check if plugin is available/configured.
        
        Returns:
            True if plugin can be used
        """
        return True

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Optional path to the directory containing workflow definitions for this plugin.

        Returns:
            Path to workflows directory or None if the plugin doesn't provide any.
        """
        return None

    def filter_workflows(self, workflows: list, plugin_config: dict) -> list:
        """
        Optional hook to filter this plugin's workflows based on its configuration.

        Override to show/hide workflows according to the plugin's own config.
        The default implementation returns all workflows unchanged.

        Args:
            workflows: Workflows discovered for this plugin (list of WorkflowInfo).
            plugin_config: The plugin's config dict from .titan/config.toml.

        Returns:
            Filtered list of workflows to display.
        """
        return workflows
