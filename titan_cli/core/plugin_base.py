# titan_cli/core/plugin_base.py
from abc import ABC, abstractmethod
from typing import List

class TitanPlugin(ABC):
    """
    Abstract Base Class for all Titan CLI plugins.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the plugin, used for registration and dependencies."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A short description of what the plugin does."""
        pass

    @property
    def dependencies(self) -> List[str]:
        """
        Other plugins this plugin depends on.
        
        The PluginRegistry will ensure dependencies are loaded first.
        
        Returns:
            List of plugin names (e.g., ["git"])
        """
        return []

    def initialize(self, config, secrets) -> None:
        """
        Initialize the plugin. This is where clients or services
        can be set up. This method is called by the PluginRegistry after
        all plugins have been discovered and dependencies resolved.
        
        Args:
            config: The fully loaded TitanConfig object.
            secrets: The SecretManager instance.
        
        Note: This is not abstract, as simple plugins may not need initialization.
        """
        pass

    def is_available(self) -> bool:
        """
        Check if the plugin's external dependencies are met.
        
        For example, a plugin wrapping a CLI tool would check if that
        tool is installed and on the system's PATH.
        
        Returns:
            True if the plugin is available to be used, False otherwise.
        """
        return True
