"""
Anthropic Claude Tools adapter for TitanTools.

This module provides adapters to convert TitanTools into Anthropic's tool format.
Implements the ToolAdapter protocol.
"""

from __future__ import annotations

from typing import Any


class AnthropicAdapter:
    """
    Adapter for Anthropic Claude API.
    
    Implements the ToolAdapter protocol to convert TitanTools into
    Anthropic's tool calling format.
    """
    
    @staticmethod
    def convert_tool(titan_tool: TitanTool) -> dict[str, Any]:
        """
        Convert a TitanTool to Anthropic's tool format.
        
        Args:
            titan_tool: The TitanTool to convert
        
        Returns:
            Dictionary in Anthropic tool format
        
        Example:
            {
                "name": "read_file",
                "description": "Reads a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path"
                        }
                    },
                    "required": ["path"]
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
            "name": titan_tool.name,
            "description": titan_tool.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
    
    @staticmethod
    def convert_tools(titan_tools: list[TitanTool]) -> list[dict[str, Any]]:
        """
        Convert a list of TitanTools to Anthropic tool format.
        
        Args:
            titan_tools: List of TitanTools to convert
        
        Returns:
            List of tool definitions in Anthropic format
        """
        return [AnthropicAdapter.convert_tool(tool) for tool in titan_tools]
    
    @staticmethod
    def execute_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        tools: list[TitanTool],
    ) -> Any:
        """
        Execute a tool use from Anthropic's response.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tools: List of available TitanTools
        
        Returns:
            The result of the tool execution
        
        Raises:
            ValueError: If the tool is not found
        """
        tool = next((t for t in tools if t.name == tool_name), None)
        
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        return tool.execute(**tool_input)


# Backward compatibility aliases
def to_anthropic_tool(titan_tool: TitanTool) -> dict[str, Any]:
    """Legacy function - use AnthropicAdapter.convert_tool() instead."""
    return AnthropicAdapter.convert_tool(titan_tool)


def to_anthropic_tools(titan_tools: list[TitanTool]) -> list[dict[str, Any]]:
    """Legacy function - use AnthropicAdapter.convert_tools() instead."""
    return AnthropicAdapter.convert_tools(titan_tools)


def execute_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    tools: list[TitanTool],
) -> Any:
    """Legacy function - use AnthropicAdapter.execute_tool() instead."""
    return AnthropicAdapter.execute_tool(tool_name, tool_input, tools)
