"""
TAP (Titan Adapter Protocol) - Main API

Simplified imports for TAP architecture components.

Example:
    from titan_cli.tap import TAPManager

    # Create TAP manager
    tap = TAPManager.from_config("config/tap/adapters.yml")

    # Get adapter
    adapter = tap.get("anthropic")

    # Convert tools
    adapted_tools = adapter.convert_tools(tools)
"""

# Import core TAP components with TAP-prefixed aliases
from titan_cli.tap.protocol import ToolAdapter as TAPProtocol
from titan_cli.tap.registry import AdapterRegistry as TAPRegistry
from titan_cli.tap.loader import AdapterLoader as TAPLoader
from titan_cli.tap.factory import AdapterFactory as TAPFactory
from titan_cli.tap.manager import AdapterManager as TAPManager

# Import verification utilities
from titan_cli.tap.protocol import (
    verify_adapter as verify_tap_adapter,
    is_valid_adapter as is_valid_tap_adapter,
    get_adapter_info as get_tap_adapter_info
)

# Keep original names for backward compatibility
from titan_cli.tap.protocol import ToolAdapter
from titan_cli.tap.registry import AdapterRegistry
from titan_cli.tap.loader import AdapterLoader
from titan_cli.tap.factory import AdapterFactory
from titan_cli.tap.manager import AdapterManager

__all__ = [
    # TAP-prefixed (recommended)
    "TAPProtocol",
    "TAPRegistry",
    "TAPLoader",
    "TAPFactory",
    "TAPManager",
    "verify_tap_adapter",
    "is_valid_tap_adapter",
    "get_tap_adapter_info",

    # Original names (backward compatibility)
    "ToolAdapter",
    "AdapterRegistry",
    "AdapterLoader",
    "AdapterFactory",
    "AdapterManager",
]

__version__ = "1.0.0"
__protocol__ = "TAP"
