"""
TAP (Titan Adapter Protocol) - Protocol definition for framework adapters.

This module defines the TAP protocol interface that all adapters must implement.
Using Protocol allows for structural subtyping (duck typing with type checking).

TAP enables framework-agnostic adapter development with zero coupling.
"""

from __future__ import annotations

import inspect
from typing import Protocol, Any, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from titan_cli.core.plugins.tool_base import TitanTool


@runtime_checkable
class ToolAdapter(Protocol):
    """
    TAP (Titan Adapter Protocol) interface for framework adapters.

    All TAP-compliant adapters must implement these methods to convert TitanTools
    into their respective framework's format.

    TAP uses Protocol for structural subtyping - any class that implements
    these methods is considered a valid TAP adapter, without needing to
    inherit from a base class.

    Example:
        class MyFrameworkAdapter:
            @staticmethod
            def convert_tool(titan_tool: TitanTool) -> dict[str, Any]:
                return {"name": titan_tool.name, ...}

            @staticmethod
            def convert_tools(titan_tools: list[TitanTool]) -> list[dict[str, Any]]:
                return [MyFrameworkAdapter.convert_tool(t) for t in titan_tools]

            @staticmethod
            def execute_tool(tool_name: str, tool_input: dict[str, Any],
                           tools: list[TitanTool]) -> Any:
                tool = next(t for t in tools if t.name == tool_name)
                return tool.execute(**tool_input)

        # MyFrameworkAdapter is now a valid ToolAdapter without inheritance!
    """

    @staticmethod
    def convert_tool(titan_tool: Any) -> Any:
        """
        Convert a single TitanTool to the framework's format.

        Args:
            titan_tool: The TitanTool to convert

        Returns:
            Tool definition in the target framework's format.
            Can be a dict, object, or any framework-specific type.
        """
        ...

    @staticmethod
    def convert_tools(titan_tools: list[Any]) -> Any:
        """
        Convert a list of TitanTools to the framework's format.

        Args:
            titan_tools: List of TitanTools to convert

        Returns:
            List or collection of tools in the target framework's format
        """
        ...

    @staticmethod
    def execute_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        tools: list[Any],
    ) -> Any:
        """
        Execute a tool based on the framework's response.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tools: List of available TitanTools

        Returns:
            The result of the tool execution

        Raises:
            ValueError: If the tool is not found
        """
        ...


def verify_adapter(adapter_class: type, strict: bool = False) -> bool:
    """
    Verify that a class implements the ToolAdapter protocol.

    Args:
        adapter_class: The class to verify
        strict: If True, also validates method signatures match protocol

    Returns:
        True if the class implements all required methods

    Example:
        if verify_adapter(AnthropicAdapter):
            print("AnthropicAdapter is valid!")

        # Strict mode validates signatures
        if verify_adapter(AnthropicAdapter, strict=True):
            print("AnthropicAdapter fully complies with protocol!")
    """
    # Quick check using runtime_checkable Protocol
    try:
        if not isinstance(adapter_class, type):
            return False

        # Use Protocol's runtime check
        if not issubclass(adapter_class, ToolAdapter):
            return False
    except TypeError:
        return False

    # Strict mode: verify method signatures
    if strict:
        return _verify_method_signatures(adapter_class)

    return True


def _verify_method_signatures(adapter_class: type) -> bool:
    """
    Verify that adapter methods have correct signatures.

    Args:
        adapter_class: The adapter class to verify

    Returns:
        True if all method signatures match the protocol
    """
    # Expected signatures for each method
    expected_methods = {
        "convert_tool": ["titan_tool"],
        "convert_tools": ["titan_tools"],
        "execute_tool": ["tool_name", "tool_input", "tools"],
    }

    for method_name, expected_params in expected_methods.items():
        if not hasattr(adapter_class, method_name):
            return False

        method = getattr(adapter_class, method_name)
        if not callable(method):
            return False

        try:
            sig = inspect.signature(method)
            actual_params = [
                p for p in sig.parameters.keys()
                if p not in ("self", "cls")
            ]

            # Check parameter names match
            if actual_params != expected_params:
                return False

        except (ValueError, TypeError):
            return False

    return True


def is_valid_adapter(obj: Any) -> bool:
    """
    Check if an object or class is a valid ToolAdapter.

    Works with both classes and instances. Uses Protocol's
    runtime_checkable decorator for validation.

    Args:
        obj: Object or class to validate

    Returns:
        True if obj implements the ToolAdapter protocol

    Example:
        # Check a class
        if is_valid_adapter(AnthropicAdapter):
            print("Class is valid!")

        # Check an instance
        adapter = AnthropicAdapter()
        if is_valid_adapter(adapter):
            print("Instance is valid!")

        # Check at runtime
        def process_with_adapter(adapter: Any):
            if not is_valid_adapter(adapter):
                raise TypeError("Invalid adapter provided")
            # Safe to use adapter here
            adapter.convert_tool(tool)
    """
    try:
        # For classes
        if isinstance(obj, type):
            return issubclass(obj, ToolAdapter)

        # For instances
        return isinstance(obj, ToolAdapter)
    except TypeError:
        return False


def get_adapter_info(adapter_class: type) -> dict[str, Any]:
    """
    Get detailed information about an adapter implementation.

    Args:
        adapter_class: The adapter class to inspect

    Returns:
        Dictionary with adapter metadata

    Example:
        info = get_adapter_info(AnthropicAdapter)
        print(f"Valid: {info['is_valid']}")
        print(f"Methods: {info['methods']}")
    """
    info = {
        "is_valid": verify_adapter(adapter_class),
        "is_strict_valid": verify_adapter(adapter_class, strict=True),
        "methods": {},
        "class_name": adapter_class.__name__,
        "module": adapter_class.__module__,
    }

    # Inspect each required method
    for method_name in ["convert_tool", "convert_tools", "execute_tool"]:
        if hasattr(adapter_class, method_name):
            method = getattr(adapter_class, method_name)
            try:
                sig = inspect.signature(method)
                info["methods"][method_name] = {
                    "exists": True,
                    "is_static": isinstance(
                        inspect.getattr_static(adapter_class, method_name),
                        staticmethod
                    ),
                    "signature": str(sig),
                    "parameters": list(sig.parameters.keys()),
                }
            except (ValueError, TypeError) as e:
                info["methods"][method_name] = {
                    "exists": True,
                    "error": str(e),
                }
        else:
            info["methods"][method_name] = {"exists": False}

    return info
