"""
Adapter Registry for managing and discovering adapters.

This module provides a centralized registry for adapter management with:
- Auto-discovery via entry points
- Protocol validation
- Thread-safe registration
- Singleton pattern
"""

from __future__ import annotations

import importlib
import logging
from typing import Optional
from threading import Lock

from titan_cli.tap.protocol import ToolAdapter, verify_adapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Singleton registry for managing tool adapters.
    
    This registry provides a centralized location for adapter management,
    ensuring that all adapters implement the ToolAdapter protocol.
    
    Best Practices:
    - Thread-safe operations with locks
    - Lazy loading of adapters
    - Protocol validation on registration
    - Clear error messages
    
    Example:
        registry = AdapterRegistry.get_instance()
        registry.register("anthropic", AnthropicAdapter)
        adapter = registry.get("anthropic")
    """
    
    _instance: Optional['AdapterRegistry'] = None
    _lock: Lock = Lock()
    
    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        self._adapters: dict[str, type] = {}
        self._metadata: dict[str, dict] = {}
        self._lazy_loaders: dict[str, str] = {}
        logger.debug("AdapterRegistry initialized")
    
    @classmethod
    def get_instance(cls) -> 'AdapterRegistry':
        """
        Get the singleton instance of the registry.
        
        Thread-safe singleton implementation using double-checked locking.
        
        Returns:
            The singleton AdapterRegistry instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance (useful for testing).
        
        Warning: This should only be used in tests!
        """
        with cls._lock:
            cls._instance = None
    
    def register(
        self,
        name: str,
        adapter_class: type,
        metadata: Optional[dict] = None,
        force: bool = False
    ) -> None:
        """
        Register an adapter class with the registry.
        
        Args:
            name: Unique identifier for the adapter
            adapter_class: The adapter class to register
            metadata: Optional metadata about the adapter
            force: If True, override existing registration
        
        Raises:
            ValueError: If adapter doesn't implement ToolAdapter protocol
            KeyError: If name already exists and force=False
        
        Example:
            registry.register(
                "anthropic",
                AnthropicAdapter,
                metadata={"version": "1.0.0", "provider": "Anthropic"}
            )
        """
        # Check if already registered
        if name in self._adapters and not force:
            raise KeyError(
                f"Adapter '{name}' is already registered. "
                f"Use force=True to override."
            )
        
        # Validate protocol implementation
        if not verify_adapter(adapter_class):
            raise ValueError(
                f"Adapter '{name}' does not implement the ToolAdapter protocol. "
                f"Required methods: convert_tool, convert_tools, execute_tool"
            )
        
        # Register the adapter
        with self._lock:
            self._adapters[name] = adapter_class
            self._metadata[name] = metadata or {}
        
        logger.info(f"Registered adapter: {name} ({adapter_class.__name__})")
    
    def register_lazy(
        self,
        name: str,
        module_path: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Register an adapter for lazy loading.
        
        The adapter will only be imported when first accessed.
        
        Args:
            name: Unique identifier for the adapter
            module_path: Full module path (e.g., 'titan.adapters.AnthropicAdapter')
            metadata: Optional metadata about the adapter
        
        Example:
            registry.register_lazy(
                "anthropic",
                "titan.adapters.anthropic.AnthropicAdapter"
            )
        """
        with self._lock:
            self._lazy_loaders[name] = module_path
            self._metadata[name] = metadata or {}
        
        logger.debug(f"Registered lazy adapter: {name} -> {module_path}")
    
    def get(self, name: str) -> type:
        """
        Get an adapter class by name.
        
        If the adapter was registered lazily, it will be loaded on first access.
        
        Args:
            name: The adapter name
        
        Returns:
            The adapter class
        
        Raises:
            KeyError: If adapter is not registered
            ImportError: If lazy loading fails
        
        Example:
            adapter = registry.get("anthropic")
            tools = adapter.convert_tools(titan_tools)
        """
        # Check if already loaded
        if name in self._adapters:
            return self._adapters[name]
        
        # Try lazy loading
        if name in self._lazy_loaders:
            module_path = self._lazy_loaders[name]
            logger.debug(f"Lazy loading adapter: {name} from {module_path}")
            
            try:
                adapter_class = self._load_class(module_path)
                # Register it for future use
                self.register(name, adapter_class, self._metadata.get(name), force=True)
                return adapter_class
            except Exception as e:
                logger.error(f"Failed to lazy load adapter '{name}': {e}")
                raise ImportError(
                    f"Failed to load adapter '{name}' from '{module_path}': {e}"
                )
        
        # Not found
        available = self.list_adapters()
        raise KeyError(
            f"Adapter '{name}' not found. Available adapters: {available}"
        )
    
    def _load_class(self, module_path: str) -> type:
        """
        Load a class from a module path.
        
        Args:
            module_path: Full path like 'titan.adapters.anthropic.AnthropicAdapter'
        
        Returns:
            The loaded class
        """
        module_name, class_name = module_path.rsplit('.', 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    
    def unregister(self, name: str) -> None:
        """
        Unregister an adapter.
        
        Args:
            name: The adapter name to remove
        
        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._adapters and name not in self._lazy_loaders:
                raise KeyError(f"Adapter '{name}' is not registered")
            
            self._adapters.pop(name, None)
            self._lazy_loaders.pop(name, None)
            self._metadata.pop(name, None)
        
        logger.info(f"Unregistered adapter: {name}")
    
    def is_registered(self, name: str) -> bool:
        """
        Check if an adapter is registered.
        
        Args:
            name: The adapter name
        
        Returns:
            True if registered (loaded or lazy), False otherwise
        """
        return name in self._adapters or name in self._lazy_loaders
    
    def list_adapters(self) -> list[str]:
        """
        List all registered adapter names.
        
        Returns:
            List of adapter names (both loaded and lazy)
        """
        loaded = set(self._adapters.keys())
        lazy = set(self._lazy_loaders.keys())
        return sorted(loaded | lazy)
    
    def get_metadata(self, name: str) -> dict:
        """
        Get metadata for an adapter.
        
        Args:
            name: The adapter name
        
        Returns:
            Metadata dictionary
        
        Raises:
            KeyError: If adapter is not registered
        """
        if not self.is_registered(name):
            raise KeyError(f"Adapter '{name}' is not registered")
        
        return self._metadata.get(name, {}).copy()
    
    def auto_discover(self, package: str = "titan.adapters") -> int:
        """
        Auto-discover adapters in a package.
        
        Scans for classes that implement the ToolAdapter protocol.
        
        Args:
            package: Package to scan for adapters
        
        Returns:
            Number of adapters discovered
        
        Example:
            discovered = registry.auto_discover("titan.adapters")
            print(f"Discovered {discovered} adapters")
        """
        discovered = 0
        
        try:
            module = importlib.import_module(package)
            
            # Get all attributes from the module
            for attr_name in dir(module):
                if attr_name.startswith('_'):
                    continue
                
                attr = getattr(module, attr_name)
                
                # Check if it's a class and implements the protocol
                if isinstance(attr, type) and verify_adapter(attr):
                    # Use lowercase class name without 'Adapter' suffix
                    adapter_name = attr_name.lower().replace('adapter', '')
                    
                    if not self.is_registered(adapter_name):
                        self.register(
                            adapter_name,
                            attr,
                            metadata={"auto_discovered": True, "package": package}
                        )
                        discovered += 1
        
        except ImportError as e:
            logger.warning(f"Failed to auto-discover in {package}: {e}")
        
        return discovered
    
    def __repr__(self) -> str:
        """String representation of the registry."""
        adapters = self.list_adapters()
        return f"AdapterRegistry({len(adapters)} adapters: {adapters})"


# Convenience function for getting the global registry
def get_registry() -> AdapterRegistry:
    """
    Get the global adapter registry instance.
    
    Returns:
        The singleton AdapterRegistry
    
    Example:
        from titan_cli.tap.registry import get_registry
        
        registry = get_registry()
        registry.register("my_adapter", MyAdapter)
    """
    return AdapterRegistry.get_instance()
