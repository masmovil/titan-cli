"""
OpenAI Function Calling adapter for TitanTools.

This module provides adapters to convert TitanTools into OpenAI function calling format.
Implements the ToolAdapter protocol.
"""

from __future__ import annotations

from typing import Any


class OpenAIAdapter:
    """
    Adapter for OpenAI API.
    
    Implements the ToolAdapter protocol to convert TitanTools into
    OpenAI's function calling format.
    """
    
    @staticmethod
    def convert_tool(titan_tool: TitanTool) -> dict[str, Any]:
        """
        Convert a TitanTool to OpenAI function calling format.
        
        Args:
            titan_tool: The TitanTool to convert
        
        Returns:
            Dictionary in OpenAI function calling format
        
        Example:
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Reads a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"}
                        },
                        "required": ["path"]
                    }
                }
            }
        """
        properties = {}
        required = []
        
        for param_name, param in titan_tool.schema.parameters.items():
            # Map Python types to JSON Schema types
            type_mapping = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "list": "array",
                "dict": "object",
            }
            
            json_type = type_mapping.get(param.type_hint.lower(), "string")
            
            properties[param_name] = {
                "type": json_type,
                "description": param.description or f"Parameter {param_name}",
            }
            
            if param.required:
                required.append(param_name)
        
        return {
            "type": "function",
            "function": {
                "name": titan_tool.name,
                "description": titan_tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
    
    @staticmethod
    def convert_tools(titan_tools: list[TitanTool]) -> list[dict[str, Any]]:
        """
        Convert a list of TitanTools to OpenAI function calling format.
        
        Args:
            titan_tools: List of TitanTools to convert
        
        Returns:
            List of function definitions in OpenAI format
        """
        return [OpenAIAdapter.convert_tool(tool) for tool in titan_tools]
    
    @staticmethod
    def execute_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        tools: list[TitanTool],
    ) -> Any:
        """
        Execute a function call from OpenAI's response.
        
        Args:
            tool_name: Name of the function to call
            tool_input: Arguments for the function
            tools: List of available TitanTools
        
        Returns:
            The result of the function execution
        
        Raises:
            ValueError: If the function is not found
        """
        tool = next((t for t in tools if t.name == tool_name), None)
        
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        return tool.execute(**tool_input)


# Backward compatibility aliases
def to_openai_function(titan_tool: TitanTool) -> dict[str, Any]:
    """Legacy function - use OpenAIAdapter.convert_tool() instead."""
    return OpenAIAdapter.convert_tool(titan_tool)


def to_openai_functions(titan_tools: list[TitanTool]) -> list[dict[str, Any]]:
    """Legacy function - use OpenAIAdapter.convert_tools() instead."""
    return OpenAIAdapter.convert_tools(titan_tools)


def execute_function_call(
    function_name: str,
    function_args: dict[str, Any],
    tools: list[TitanTool],
) -> Any:
    """Legacy function - use OpenAIAdapter.execute_tool() instead."""
    return OpenAIAdapter.execute_tool(function_name, function_args, tools)
