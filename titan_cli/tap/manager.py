"""
Adapter Manager - Complete lifecycle management for adapters.

This is the main interface for working with adapters, combining:
- Registry for discovery
- Loader for configuration
- Factory for instantiation
- Strategy pattern for runtime selection
- Hot-reload capabilities

Best practices:
- Single entry point for adapter management
- Facade pattern for simplicity
- Strategy pattern for flexibility
- Clear error handling
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union, Any

from titan_cli.tap.registry import AdapterRegistry, get_registry
from titan_cli.tap.loader import AdapterLoader
from titan_cli.tap.factory import AdapterFactory

logger = logging.getLogger(__name__)


class AdapterManager:
    """
    Complete adapter lifecycle management.
    
    This is the main interface you should use. It provides:
    - Auto-discovery of adapters
    - Configuration-based loading
    - Dynamic instantiation
    - Strategy/fallback patterns
    - Hot-reload capabilities
    
    Best Practices:
    - Use this as your primary adapter interface
    - Configure once, use everywhere
    - Leverage fallback strategies
    - Enable hot-reload in development
    
    Example:
        # Simple usage
        manager = AdapterManager()
        manager.load_config("config/adapters.yml")
        adapter = manager.get("anthropic")
        
        # With fallback
        adapter = manager.get_with_fallback(["anthropic", "openai"])
        
        # From config file
        manager = AdapterManager.from_config("config/adapters.yml")
    """
    
    def __init__(
        self,
        registry: Optional[AdapterRegistry] = None,
        cache_instances: bool = True,
        auto_discover: bool = True
    ):
        """
        Initialize the adapter manager.
        
        Args:
            registry: Optional registry instance
            cache_instances: Whether to cache adapter instances
            auto_discover: Whether to auto-discover built-in adapters
        """
        self.registry = registry or get_registry()
        self.loader = AdapterLoader(self.registry)
        self.factory = AdapterFactory(self.registry, cache_instances)
        
        if auto_discover:
            self._auto_discover_builtin()
        
        logger.info("AdapterManager initialized")
    
    def _auto_discover_builtin(self) -> None:
        """Auto-discover built-in adapters."""
        try:
            discovered = self.registry.auto_discover("titan_cli.tap")
            logger.info(f"Auto-discovered {discovered} built-in adapters")
        except Exception as e:
            logger.warning(f"Auto-discovery failed: {e}")
    
    @classmethod
    def from_config(
        cls,
        config_path: Union[str, Path],
        env: Optional[str] = None,
        **kwargs
    ) -> 'AdapterManager':
        """
        Create a manager and load configuration in one step.
        
        Args:
            config_path: Path to configuration file (YAML or JSON)
            env: Optional environment name
            **kwargs: Additional arguments for AdapterManager
        
        Returns:
            Configured AdapterManager instance
        
        Example:
            manager = AdapterManager.from_config("config/adapters.yml")
            manager = AdapterManager.from_config("config/adapters.yml", env="prod")
        """
        manager = cls(**kwargs)
        manager.load_config(config_path, env)
        return manager
    
    def load_config(
        self,
        config_path: Union[str, Path],
        env: Optional[str] = None
    ) -> int:
        """
        Load adapters from a configuration file.
        
        Supports YAML and JSON formats. File type detected by extension.
        
        Args:
            config_path: Path to configuration file
            env: Optional environment name for env-specific config
        
        Returns:
            Number of adapters loaded
        
        Example:
            manager.load_config("config/adapters.yml")
            manager.load_config("config/adapters.json", env="prod")
        """
        config_path = Path(config_path)
        
        if config_path.suffix in ['.yml', '.yaml']:
            return self.loader.load_from_yaml(config_path, env)
        elif config_path.suffix == '.json':
            return self.loader.load_from_json(config_path, env)
        else:
            raise ValueError(
                f"Unsupported config format: {config_path.suffix}. "
                f"Use .yml, .yaml, or .json"
            )
    
    def load_from_env(
        self,
        prefix: str = "TITAN_ADAPTER_"
    ) -> int:
        """
        Load adapter configuration from environment variables.
        
        Args:
            prefix: Prefix for environment variables
        
        Returns:
            Number of adapters loaded
        
        Example:
            # With env vars:
            # TITAN_ADAPTER_ANTHROPIC__MODULE=titan_cli.tap.AnthropicAdapter
            # TITAN_ADAPTER_ANTHROPIC__ENABLED=true
            
            manager.load_from_env()
        """
        return self.loader.load_from_env(prefix)
    
    def get(
        self,
        name: str,
        use_cache: Optional[bool] = None,
        **config
    ) -> Any:
        """
        Get an adapter instance.
        
        Args:
            name: Adapter name
            use_cache: Override caching behavior
            **config: Configuration parameters
        
        Returns:
            Adapter instance or class
        
        Example:
            adapter = manager.get("anthropic")
            tools = adapter.convert_tools(titan_tools)
        """
        return self.factory.create(name, use_cache, **config)
    
    def get_with_fallback(
        self,
        names: list[str],
        **config
    ) -> tuple[str, Any]:
        """
        Get adapter with fallback options.
        
        Tries each adapter in order until one succeeds.
        
        Args:
            names: List of adapter names to try
            **config: Configuration parameters
        
        Returns:
            Tuple of (adapter_name, adapter_instance)
        
        Example:
            name, adapter = manager.get_with_fallback([
                "anthropic",
                "openai",
                "local"
            ])
            print(f"Using: {name}")
        """
        return self.factory.create_with_fallback(names, **config)
    
    def list_adapters(self) -> list[str]:
        """
        List all registered adapters.
        
        Returns:
            List of adapter names
        """
        return self.registry.list_adapters()
    
    def is_available(self, name: str) -> bool:
        """
        Check if an adapter is available.
        
        Args:
            name: Adapter name
        
        Returns:
            True if adapter is registered
        """
        return self.registry.is_registered(name)
    
    def get_metadata(self, name: str) -> dict[str, Any]:
        """
        Get metadata for an adapter.
        
        Args:
            name: Adapter name
        
        Returns:
            Metadata dictionary
        """
        return self.registry.get_metadata(name)
    
    def reload(self, name: str) -> None:
        """
        Hot-reload an adapter.
        
        Useful for development or when configuration changes.
        
        Args:
            name: Adapter name to reload
        
        Example:
            # After modifying AnthropicAdapter code:
            manager.reload("anthropic")
        """
        # Clear from factory cache
        self.factory.clear_cache(name)
        
        # Unregister and re-register (forces re-import)
        if self.registry.is_registered(name):
            metadata = self.registry.get_metadata(name)
            lazy_loader = self.registry._lazy_loaders.get(name)
            
            self.registry.unregister(name)
            
            if lazy_loader:
                # Re-register as lazy
                self.registry.register_lazy(name, lazy_loader, metadata)
            
            logger.info(f"Reloaded adapter: {name}")
        else:
            logger.warning(f"Cannot reload unregistered adapter: {name}")
    
    def reload_all(self) -> None:
        """
        Hot-reload all adapters.
        
        Useful when switching environments or after major configuration changes.
        """
        adapters = self.list_adapters()
        for name in adapters:
            try:
                self.reload(name)
            except Exception as e:
                logger.error(f"Failed to reload '{name}': {e}")
        
        logger.info(f"Reloaded {len(adapters)} adapters")
    
    def register_strategy(
        self,
        strategy_name: str,
        adapter_names: list[str]
    ) -> None:
        """
        Register a named strategy (list of adapters to try).
        
        Useful for common fallback patterns.
        
        Args:
            strategy_name: Name for the strategy
            adapter_names: List of adapter names in priority order
        
        Example:
            manager.register_strategy("production", [
                "anthropic",
                "openai"
            ])
            
            manager.register_strategy("development", [
                "local",
                "anthropic"
            ])
            
            name, adapter = manager.use_strategy("production")
        """
        if not hasattr(self, '_strategies'):
            self._strategies = {}
        
        self._strategies[strategy_name] = adapter_names
        logger.info(f"Registered strategy '{strategy_name}': {adapter_names}")
    
    def use_strategy(
        self,
        strategy_name: str,
        **config
    ) -> tuple[str, Any]:
        """
        Use a registered strategy.
        
        Args:
            strategy_name: Strategy name
            **config: Configuration parameters
        
        Returns:
            Tuple of (adapter_name, adapter_instance)
        
        Raises:
            KeyError: If strategy not found
        
        Example:
            name, adapter = manager.use_strategy("production")
        """
        if not hasattr(self, '_strategies'):
            raise KeyError(f"No strategies registered")
        
        if strategy_name not in self._strategies:
            available = list(self._strategies.keys())
            raise KeyError(
                f"Strategy '{strategy_name}' not found. "
                f"Available: {available}"
            )
        
        adapter_names = self._strategies[strategy_name]
        return self.get_with_fallback(adapter_names, **config)
    
    def create_example_config(
        self,
        filepath: Union[str, Path],
        format: str = "yaml"
    ) -> None:
        """
        Create an example configuration file.
        
        Args:
            filepath: Where to save the example
            format: 'yaml' or 'json'
        
        Example:
            manager.create_example_config("config/adapters.example.yml")
        """
        AdapterLoader.create_example_config(filepath, format)
    
    def __repr__(self) -> str:
        """String representation."""
        adapters = self.list_adapters()
        return (
            f"AdapterManager("
            f"{len(adapters)} adapters: {adapters})"
        )
