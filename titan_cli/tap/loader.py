"""
Adapter Loader for dynamic configuration-based loading.

This module provides loaders for different configuration formats:
- YAML files
- JSON files
- Python dictionaries
- Environment variables

Best practices:
- Validation before loading
- Clear error messages
- Support for multiple sources
- Schema validation
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

from titan_cli.tap.registry import AdapterRegistry, get_registry

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass


class AdapterLoader:
    """
    Load and configure adapters from various sources.
    
    Supports:
    - YAML configuration files
    - JSON configuration files
    - Python dictionaries
    - Environment-based configuration
    
    Best Practices:
    - Validate configuration schema
    - Provide helpful error messages
    - Support multiple environments
    - Fail fast with clear errors
    
    Example:
        loader = AdapterLoader()
        loader.load_from_yaml("config/adapters.yml")
    """
    
    def __init__(self, registry: Optional[AdapterRegistry] = None):
        """
        Initialize the loader.
        
        Args:
            registry: Optional registry instance. Uses global if not provided.
        """
        self.registry = registry or get_registry()
        logger.debug("AdapterLoader initialized")
    
    def load_from_yaml(
        self,
        filepath: Union[str, Path],
        env: Optional[str] = None
    ) -> int:
        """
        Load adapters from a YAML configuration file.
        
        Args:
            filepath: Path to the YAML file
            env: Optional environment name (dev, prod, test)
        
        Returns:
            Number of adapters loaded
        
        Raises:
            ImportError: If PyYAML is not installed
            FileNotFoundError: If file doesn't exist
            ConfigurationError: If configuration is invalid
        
        Example:
            loader.load_from_yaml("config/adapters.yml")
            loader.load_from_yaml("config/adapters.yml", env="prod")
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is not installed. Install it with: pip install pyyaml"
            )
        
        filepath = Path(filepath)
        
        # Try environment-specific file first
        if env:
            env_filepath = filepath.parent / f"{filepath.stem}.{env}{filepath.suffix}"
            if env_filepath.exists():
                filepath = env_filepath
                logger.info(f"Using environment-specific config: {filepath}")
        
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        logger.info(f"Loading adapters from YAML: {filepath}")
        
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f)
        
        return self._load_from_dict(config, source=str(filepath))
    
    def load_from_json(
        self,
        filepath: Union[str, Path],
        env: Optional[str] = None
    ) -> int:
        """
        Load adapters from a JSON configuration file.
        
        Args:
            filepath: Path to the JSON file
            env: Optional environment name
        
        Returns:
            Number of adapters loaded
        
        Example:
            loader.load_from_json("config/adapters.json")
        """
        filepath = Path(filepath)
        
        # Try environment-specific file first
        if env:
            env_filepath = filepath.parent / f"{filepath.stem}.{env}{filepath.suffix}"
            if env_filepath.exists():
                filepath = env_filepath
                logger.info(f"Using environment-specific config: {filepath}")
        
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        logger.info(f"Loading adapters from JSON: {filepath}")
        
        with open(filepath, 'r') as f:
            config = json.load(f)
        
        return self._load_from_dict(config, source=str(filepath))
    
    def load_from_dict(self, config: dict[str, Any]) -> int:
        """
        Load adapters from a Python dictionary.
        
        Args:
            config: Configuration dictionary
        
        Returns:
            Number of adapters loaded
        
        Example:
            config = {
                "adapters": [
                    {"name": "anthropic", "module": "titan_cli.tap.AnthropicAdapter"}
                ]
            }
            loader.load_from_dict(config)
        """
        return self._load_from_dict(config, source="dict")
    
    def _load_from_dict(self, config: dict[str, Any], source: str = "unknown") -> int:
        """
        Internal method to load from a validated dictionary.
        
        Args:
            config: Configuration dictionary
            source: Source description for error messages
        
        Returns:
            Number of adapters loaded
        """
        # Validate configuration structure
        self._validate_config(config, source)
        
        adapters_config = config.get("adapters", [])
        loaded = 0
        
        for adapter_cfg in adapters_config:
            try:
                self._load_adapter(adapter_cfg)
                loaded += 1
            except Exception as e:
                logger.error(
                    f"Failed to load adapter from {source}: {adapter_cfg.get('name', 'unknown')}"
                )
                logger.error(f"Error: {e}")
                # Continue loading other adapters
        
        logger.info(f"Loaded {loaded}/{len(adapters_config)} adapters from {source}")
        return loaded
    
    def _validate_config(self, config: dict[str, Any], source: str) -> None:
        """
        Validate configuration structure.
        
        Args:
            config: Configuration to validate
            source: Source description for error messages
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not isinstance(config, dict):
            raise ConfigurationError(
                f"Configuration from {source} must be a dictionary, got {type(config)}"
            )
        
        if "adapters" not in config:
            raise ConfigurationError(
                f"Configuration from {source} must have an 'adapters' key"
            )
        
        adapters = config["adapters"]
        if not isinstance(adapters, list):
            raise ConfigurationError(
                f"'adapters' in {source} must be a list, got {type(adapters)}"
            )
    
    def _load_adapter(self, adapter_config: dict[str, Any]) -> None:
        """
        Load a single adapter from configuration.
        
        Args:
            adapter_config: Adapter configuration dictionary
        
        Raises:
            ConfigurationError: If adapter configuration is invalid
        """
        # Validate required fields
        if "name" not in adapter_config:
            raise ConfigurationError("Adapter configuration must have a 'name' field")
        
        if "module" not in adapter_config:
            raise ConfigurationError(
                f"Adapter '{adapter_config['name']}' must have a 'module' field"
            )
        
        name = adapter_config["name"]
        module_path = adapter_config["module"]
        metadata = adapter_config.get("metadata", {})
        config_params = adapter_config.get("config", {})
        
        # Add config params to metadata
        if config_params:
            metadata["config"] = config_params
        
        # Add source information
        metadata["loaded_from_config"] = True
        
        # Register with lazy loading
        self.registry.register_lazy(name, module_path, metadata)
        logger.debug(f"Configured adapter: {name} -> {module_path}")
    
    def load_from_env(
        self,
        prefix: str = "TITAN_ADAPTER_",
        delimiter: str = "__"
    ) -> int:
        """
        Load adapter configuration from environment variables.
        
        Environment variables should follow the pattern:
        {PREFIX}{ADAPTER_NAME}{DELIMITER}{KEY}
        
        Example:
            TITAN_ADAPTER_ANTHROPIC__MODULE=titan_cli.tap.AnthropicAdapter
            TITAN_ADAPTER_ANTHROPIC__ENABLED=true
        
        Args:
            prefix: Prefix for environment variables
            delimiter: Delimiter between adapter name and config key
        
        Returns:
            Number of adapters configured
        """
        adapters_config: dict[str, dict[str, str]] = {}
        
        # Parse environment variables
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            
            # Extract adapter name and config key
            rest = key[len(prefix):]
            if delimiter not in rest:
                logger.warning(f"Skipping invalid env var format: {key}")
                continue
            
            adapter_name, config_key = rest.split(delimiter, 1)
            adapter_name = adapter_name.lower()
            config_key = config_key.lower()
            
            # Initialize adapter config if needed
            if adapter_name not in adapters_config:
                adapters_config[adapter_name] = {}
            
            adapters_config[adapter_name][config_key] = value
        
        # Load adapters
        loaded = 0
        for adapter_name, config in adapters_config.items():
            if "module" not in config:
                logger.warning(
                    f"Skipping adapter '{adapter_name}': missing MODULE in env vars"
                )
                continue
            
            # Check if enabled (default: true)
            if config.get("enabled", "true").lower() == "false":
                logger.info(f"Skipping disabled adapter: {adapter_name}")
                continue
            
            try:
                metadata = {k: v for k, v in config.items() if k != "module"}
                metadata["loaded_from_env"] = True
                
                self.registry.register_lazy(
                    adapter_name,
                    config["module"],
                    metadata
                )
                loaded += 1
            except Exception as e:
                logger.error(f"Failed to load adapter '{adapter_name}' from env: {e}")
        
        logger.info(f"Loaded {loaded} adapters from environment variables")
        return loaded
    
    @staticmethod
    def create_example_config(filepath: Union[str, Path], format: str = "yaml") -> None:
        """
        Create an example configuration file.
        
        Args:
            filepath: Where to save the example
            format: 'yaml' or 'json'
        
        Example:
            AdapterLoader.create_example_config("config/adapters.example.yml")
        """
        example_config = {
            "adapters": [
                {
                    "name": "anthropic",
                    "module": "titan_cli.tap.anthropic.AnthropicAdapter",
                    "metadata": {
                        "provider": "Anthropic",
                        "version": "1.0.0"
                    },
                    "config": {
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 4096
                    }
                },
                {
                    "name": "openai",
                    "module": "titan_cli.tap.openai.OpenAIAdapter",
                    "metadata": {
                        "provider": "OpenAI",
                        "version": "1.0.0"
                    },
                    "config": {
                        "model": "gpt-4",
                        "temperature": 0.7
                    }
                },
                {
                    "name": "langraph",
                    "module": "titan_cli.tap.langraph.LangGraphAdapter",
                    "metadata": {
                        "provider": "LangChain",
                        "version": "1.0.0"
                    },
                    "config": {
                        "system_prompt": "You are a helpful assistant."
                    }
                }
            ]
        }
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "yaml":
            if not YAML_AVAILABLE:
                raise ImportError("PyYAML is required to create YAML examples")
            
            with open(filepath, 'w') as f:
                yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)
        
        elif format == "json":
            with open(filepath, 'w') as f:
                json.dump(example_config, f, indent=2)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Created example configuration: {filepath}")
