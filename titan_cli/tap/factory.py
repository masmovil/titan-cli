"""
Adapter Factory with Dependency Injection.

This module provides a factory for creating adapter instances with:
- Configuration-based instantiation
- Dependency injection
- Caching and reuse
- Strategy pattern support

Best practices:
- Factory pattern for object creation
- Dependency injection for flexibility
- Caching for performance
- Clear separation of concerns
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from typing import Any, Optional, Callable
from functools import lru_cache

from titan_cli.tap.registry import AdapterRegistry, get_registry

logger = logging.getLogger(__name__)


class AdapterFactory:
    """
    Factory for creating and managing adapter instances.
    
    Supports:
    - Lazy instantiation
    - Dependency injection
    - Configuration passing
    - Instance caching
    - Custom builders
    
    Best Practices:
    - Use factory instead of direct instantiation
    - Cache frequently-used instances
    - Inject dependencies for testability
    - Support both stateless and stateful adapters
    
    Example:
        factory = AdapterFactory()
        adapter = factory.create("anthropic", model="claude-3")
    """
    
    def __init__(
        self,
        registry: Optional[AdapterRegistry] = None,
        cache_instances: bool = True
    ):
        """
        Initialize the factory.

        Args:
            registry: Optional registry instance
            cache_instances: Whether to cache created instances
        """
        self.registry = registry or get_registry()
        self.cache_instances = cache_instances
        self._instance_cache: dict[str, Any] = {}
        self._builders: dict[str, Callable] = {}
        logger.debug(f"AdapterFactory initialized (cache={cache_instances})")
    
    def create(
        self,
        name: str,
        use_cache: Optional[bool] = None,
        **config
    ) -> Any:
        """
        Create an adapter instance.

        For stateless adapters (like current TitanAgents adapters),
        this returns the class itself since methods are @staticmethod.

        For stateful adapters, this instantiates with the provided config.

        Args:
            name: Adapter name
            use_cache: Override default caching behavior
            **config: Configuration parameters for the adapter

        Returns:
            Adapter instance or class

        Example:
            # Stateless adapter (returns class)
            adapter = factory.create("anthropic")
            tools = adapter.convert_tools(titan_tools)

            # Stateful adapter with config
            adapter = factory.create(
                "custom",
                api_key="...",
                timeout=30
            )
        """
        use_cache = use_cache if use_cache is not None else self.cache_instances
        cache_key = self._make_cache_key(name, config)

        # Check cache
        if use_cache and (cached := self._instance_cache.get(cache_key)):
            logger.debug(f"Using cached instance: {name}")
            return cached

        # Create instance
        instance = self._create_instance(name, config)

        # Cache if enabled
        if use_cache:
            self._instance_cache[cache_key] = instance

        return instance

    def _create_instance(self, name: str, config: dict[str, Any]) -> Any:
        """
        Create an adapter instance using builder or registry.

        Separated from create() for better single responsibility.

        Args:
            name: Adapter name
            config: Configuration dictionary

        Returns:
            Adapter instance or class
        """
        # Check for custom builder
        if name in self._builders:
            logger.debug(f"Using custom builder for: {name}")
            return self._builders[name](config)

        # Get adapter class from registry
        adapter_class = self.registry.get(name)

        # Most current adapters are stateless (only @staticmethod)
        # So we return the class itself
        # If adapter has __init__ that needs params, instantiate it
        if self._needs_instantiation(adapter_class):
            logger.debug(f"Instantiating stateful adapter: {name}")
            return adapter_class(**config)

        logger.debug(f"Using stateless adapter: {name}")
        return adapter_class

    def register_builder(
        self,
        name: str,
        builder: Callable[[dict[str, Any]], Any]
    ) -> None:
        """
        Register a custom builder function for an adapter.

        Useful for complex initialization logic or adapters that need
        special handling.

        Args:
            name: Adapter name
            builder: Function that takes config dict and returns instance

        Raises:
            TypeError: If builder is not callable

        Example:
            def build_complex_adapter(config):
                adapter = ComplexAdapter()
                adapter.configure(**config)
                adapter.connect()
                return adapter

            factory.register_builder("complex", build_complex_adapter)
            adapter = factory.create("complex", host="localhost")
        """
        if not callable(builder):
            raise TypeError(
                f"Builder for '{name}' must be callable, got {type(builder).__name__}"
            )

        if name in self._builders:
            logger.warning(f"Overwriting existing builder for: {name}")

        self._builders[name] = builder
        logger.info(f"Registered custom builder for: {name}")
    
    def clear_cache(self, name: Optional[str] = None) -> None:
        """
        Clear instance cache.
        
        Args:
            name: If provided, only clear cache for this adapter.
                 If None, clear all cache.
        
        Example:
            factory.clear_cache()  # Clear all
            factory.clear_cache("anthropic")  # Clear specific
        """
        if name is None:
            self._instance_cache.clear()
            logger.debug("Cleared all adapter cache")
        else:
            # Clear all cache entries for this adapter
            # Includes both simple key (name only) and complex keys (name:hash)
            keys_to_remove = [
                k for k in self._instance_cache.keys()
                if k == name or k.startswith(f"{name}:")
            ]
            for key in keys_to_remove:
                del self._instance_cache[key]
            logger.debug(f"Cleared cache for: {name}")
    
    def _make_cache_key(self, name: str, config: dict[str, Any]) -> str:
        """
        Generate a cache key from adapter name and config.

        Uses JSON serialization and MD5 hash for complex configs,
        ensuring consistent keys even with nested structures.

        Args:
            name: Adapter name
            config: Configuration dictionary

        Returns:
            Cache key string
        """
        if not config:
            return name

        # Try JSON serialization for consistent hashing
        try:
            config_json = json.dumps(config, sort_keys=True)
            config_hash = hashlib.md5(config_json.encode()).hexdigest()[:8]
            return f"{name}:{config_hash}"
        except (TypeError, ValueError):
            # Fallback for non-serializable objects
            config_items = sorted(config.items())
            config_str = "|".join(f"{k}={v}" for k, v in config_items)
            return f"{name}:{config_str}"
    
    def _needs_instantiation(self, adapter_class: type) -> bool:
        """
        Check if an adapter class needs instantiation.

        Current TitanAgents adapters are stateless with only @staticmethod,
        so they don't need instantiation. This method detects that.

        Args:
            adapter_class: The adapter class to check

        Returns:
            True if needs instantiation, False otherwise
        """
        try:
            sig = inspect.signature(adapter_class.__init__)
            params = [
                p for p in sig.parameters.values()
                if p.name != 'self' and p.default == inspect.Parameter.empty
            ]
            
            # If __init__ has required params, needs instantiation
            if params:
                return True
            
            # Check if adapter has instance methods (not just static/class methods)
            instance_methods = [
                name for name, method in inspect.getmembers(adapter_class)
                if not name.startswith('_')
                and callable(method)
                and not isinstance(inspect.getattr_static(adapter_class, name), (staticmethod, classmethod))
            ]
            
            # If has instance methods, needs instantiation
            return len(instance_methods) > 0

        except (AttributeError, TypeError, ValueError) as e:
            # If can't determine, assume stateless
            logger.debug(f"Could not inspect {adapter_class.__name__}: {e}")
            return False
    
    def create_with_fallback(
        self,
        names: list[str],
        **config
    ) -> tuple[str, Any]:
        """
        Try to create adapter with fallback options.
        
        Tries each adapter in order until one succeeds.
        
        Args:
            names: List of adapter names to try in order
            **config: Configuration for the adapters
        
        Returns:
            Tuple of (adapter_name, adapter_instance)
        
        Raises:
            RuntimeError: If all adapters fail
        
        Example:
            # Try Anthropic first, fallback to OpenAI, then local
            name, adapter = factory.create_with_fallback(
                ["anthropic", "openai", "local"]
            )
            print(f"Using adapter: {name}")
        """
        errors = []
        
        for name in names:
            try:
                adapter = self.create(name, **config)
                logger.info(f"Successfully created adapter: {name}")
                return (name, adapter)
            except Exception as e:
                logger.warning(f"Failed to create '{name}': {e}")
                errors.append((name, str(e)))
        
        # All failed
        error_details = "\n".join(f"  - {name}: {err}" for name, err in errors)
        raise RuntimeError(
            f"Failed to create adapter with fallback. Tried: {names}\n"
            f"Errors:\n{error_details}"
        )
    
    def __repr__(self) -> str:
        """String representation."""
        cached = len(self._instance_cache)
        builders = len(self._builders)
        return (
            f"AdapterFactory("
            f"cache={self.cache_instances}, "
            f"cached_instances={cached}, "
            f"custom_builders={builders})"
        )
