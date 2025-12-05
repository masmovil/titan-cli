"""
Integration tests for TAP adapters.

Tests Anthropic and OpenAI adapters with tool conversion and execution.
"""

from __future__ import annotations

import pytest
from typing import Any, Dict
from dataclasses import dataclass, field

from titan_cli.tap.registry import AdapterRegistry


# Simplified TitanTool classes for testing
@dataclass
class ToolParameter:
    """Metadata for a tool parameter."""
    type_hint: str
    description: str = ""
    required: bool = True


@dataclass
class ToolSchema:
    """Schema definition for a tool."""
    name: str
    description: str
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)


class TitanTool:
    """Base class for Titan tools (simplified for testing)."""

    def __init__(self, schema: ToolSchema):
        self.schema = schema
        self.name = schema.name
        self.description = schema.description

    def execute(self, **kwargs) -> Any:
        """Execute the tool - to be overridden."""
        raise NotImplementedError


# Mock tool for testing
class MockReadFileTool(TitanTool):
    """Mock tool for reading files."""

    def __init__(self):
        schema = ToolSchema(
            name="read_file",
            description="Reads a file from disk",
            parameters={
                "path": ToolParameter(
                    type_hint="str",
                    description="Path to the file",
                    required=True
                ),
                "encoding": ToolParameter(
                    type_hint="str",
                    description="File encoding",
                    required=False
                )
            }
        )
        super().__init__(schema)

    def execute(self, path: str, encoding: str = "utf-8") -> str:
        """Execute the tool."""
        return f"Content of {path} (encoding: {encoding})"


class MockCalculatorTool(TitanTool):
    """Mock calculator tool."""

    def __init__(self):
        schema = ToolSchema(
            name="calculator",
            description="Performs mathematical calculations",
            parameters={
                "operation": ToolParameter(
                    type_hint="str",
                    description="Operation to perform",
                    required=True
                ),
                "a": ToolParameter(
                    type_hint="int",
                    description="First number",
                    required=True
                ),
                "b": ToolParameter(
                    type_hint="int",
                    description="Second number",
                    required=True
                )
            }
        )
        super().__init__(schema)

    def execute(self, operation: str, a: int, b: int) -> int:
        """Execute the tool."""
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        elif operation == "divide":
            return a // b
        else:
            raise ValueError(f"Unknown operation: {operation}")


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before each test."""
    AdapterRegistry.reset()
    yield
    AdapterRegistry.reset()


@pytest.fixture
def sample_tools():
    """Create sample TitanTools."""
    return [MockReadFileTool(), MockCalculatorTool()]


class TestAnthropicAdapter:
    """Integration tests for Anthropic adapter."""

    @pytest.fixture
    def anthropic_adapter(self):
        """Get Anthropic adapter class."""
        from titan_cli.tap.adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter

    def test_convert_tool_basic(self, anthropic_adapter, sample_tools):
        """Test converting single tool to Anthropic format."""
        tool = sample_tools[0]  # read_file

        converted = anthropic_adapter.convert_tool(tool)

        assert "name" in converted
        assert converted["name"] == "read_file"
        assert "description" in converted
        assert converted["description"] == "Reads a file from disk"
        assert "input_schema" in converted
        assert converted["input_schema"]["type"] == "object"
        assert "path" in converted["input_schema"]["properties"]
        assert "encoding" in converted["input_schema"]["properties"]

    def test_convert_tool_with_required_params(self, anthropic_adapter, sample_tools):
        """Test that required parameters are marked correctly."""
        tool = sample_tools[0]  # read_file

        converted = anthropic_adapter.convert_tool(tool)

        assert "required" in converted["input_schema"]
        assert "path" in converted["input_schema"]["required"]
        assert "encoding" not in converted["input_schema"]["required"]

    def test_convert_tools_multiple(self, anthropic_adapter, sample_tools):
        """Test converting multiple tools."""
        converted_list = anthropic_adapter.convert_tools(sample_tools)

        assert isinstance(converted_list, list)
        assert len(converted_list) == 2
        assert converted_list[0]["name"] == "read_file"
        assert converted_list[1]["name"] == "calculator"

    def test_execute_tool_success(self, anthropic_adapter, sample_tools):
        """Test executing tool successfully."""
        tool_name = "read_file"
        tool_input = {"path": "/tmp/test.txt", "encoding": "utf-8"}

        result = anthropic_adapter.execute_tool(tool_name, tool_input, sample_tools)

        assert "Content of /tmp/test.txt" in result
        assert "utf-8" in result

    def test_execute_tool_with_defaults(self, anthropic_adapter, sample_tools):
        """Test executing tool with default parameters."""
        tool_name = "read_file"
        tool_input = {"path": "/tmp/test.txt"}

        result = anthropic_adapter.execute_tool(tool_name, tool_input, sample_tools)

        assert "Content of /tmp/test.txt" in result
        assert "utf-8" in result  # Default encoding

    def test_execute_tool_not_found(self, anthropic_adapter, sample_tools):
        """Test executing non-existent tool."""
        with pytest.raises(ValueError, match="Tool not found"):
            anthropic_adapter.execute_tool("nonexistent", {}, sample_tools)

    def test_execute_calculator_tool(self, anthropic_adapter, sample_tools):
        """Test executing calculator tool with various operations."""
        # Test addition
        result = anthropic_adapter.execute_tool(
            "calculator",
            {"operation": "add", "a": 10, "b": 5},
            sample_tools
        )
        assert result == 15

        # Test subtraction
        result = anthropic_adapter.execute_tool(
            "calculator",
            {"operation": "subtract", "a": 10, "b": 5},
            sample_tools
        )
        assert result == 5

        # Test multiplication
        result = anthropic_adapter.execute_tool(
            "calculator",
            {"operation": "multiply", "a": 10, "b": 5},
            sample_tools
        )
        assert result == 50

    def test_tool_schema_types(self, anthropic_adapter):
        """Test various parameter types in schema."""
        class TypedTool(TitanTool):
            def __init__(self):
                schema = ToolSchema(
                    name="typed_tool",
                    description="Tool with various types",
                    parameters={
                        "str_param": ToolParameter(
                            type_hint="str",
                            description="String parameter",
                            required=True
                        ),
                        "int_param": ToolParameter(
                            type_hint="int",
                            description="Integer parameter",
                            required=True
                        ),
                        "bool_param": ToolParameter(
                            type_hint="bool",
                            description="Boolean parameter",
                            required=True
                        ),
                        "float_param": ToolParameter(
                            type_hint="float",
                            description="Float parameter",
                            required=True
                        )
                    }
                )
                super().__init__(schema)

            def execute(self, **kwargs) -> str:
                return "ok"

        tool = TypedTool()
        converted = anthropic_adapter.convert_tool(tool)
        props = converted["input_schema"]["properties"]

        assert props["str_param"]["type"] == "string"
        assert props["int_param"]["type"] == "integer"
        assert props["bool_param"]["type"] == "boolean"
        assert props["float_param"]["type"] == "number"


class TestOpenAIAdapter:
    """Integration tests for OpenAI adapter."""

    @pytest.fixture
    def openai_adapter(self):
        """Get OpenAI adapter class."""
        from titan_cli.tap.adapters.openai import OpenAIAdapter
        return OpenAIAdapter

    def test_convert_tool_basic(self, openai_adapter, sample_tools):
        """Test converting single tool to OpenAI format."""
        tool = sample_tools[0]  # read_file

        converted = openai_adapter.convert_tool(tool)

        assert "type" in converted
        assert converted["type"] == "function"
        assert "function" in converted

        func = converted["function"]
        assert func["name"] == "read_file"
        assert func["description"] == "Reads a file from disk"
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"
        assert "path" in func["parameters"]["properties"]

    def test_convert_tool_with_required_params(self, openai_adapter, sample_tools):
        """Test that required parameters are marked correctly."""
        tool = sample_tools[0]  # read_file

        converted = openai_adapter.convert_tool(tool)
        func = converted["function"]

        assert "required" in func["parameters"]
        assert "path" in func["parameters"]["required"]
        assert "encoding" not in func["parameters"]["required"]

    def test_convert_tools_multiple(self, openai_adapter, sample_tools):
        """Test converting multiple tools."""
        converted_list = openai_adapter.convert_tools(sample_tools)

        assert isinstance(converted_list, list)
        assert len(converted_list) == 2
        assert converted_list[0]["function"]["name"] == "read_file"
        assert converted_list[1]["function"]["name"] == "calculator"

    def test_execute_tool_success(self, openai_adapter, sample_tools):
        """Test executing tool successfully."""
        tool_name = "read_file"
        tool_input = {"path": "/tmp/test.txt"}

        result = openai_adapter.execute_tool(tool_name, tool_input, sample_tools)

        assert "Content of /tmp/test.txt" in result

    def test_execute_calculator_tool(self, openai_adapter, sample_tools):
        """Test executing calculator tool."""
        result = openai_adapter.execute_tool(
            "calculator",
            {"operation": "add", "a": 20, "b": 15},
            sample_tools
        )
        assert result == 35

    def test_tool_schema_types(self, openai_adapter):
        """Test various parameter types in schema."""
        class TypedTool(TitanTool):
            def __init__(self):
                schema = ToolSchema(
                    name="typed_tool",
                    description="Tool with various types",
                    parameters={
                        "str_param": ToolParameter(type_hint="str", required=True),
                        "int_param": ToolParameter(type_hint="int", required=True),
                        "bool_param": ToolParameter(type_hint="bool", required=True),
                        "float_param": ToolParameter(type_hint="float", required=True)
                    }
                )
                super().__init__(schema)

            def execute(self, **kwargs) -> str:
                return "ok"

        tool = TypedTool()
        converted = openai_adapter.convert_tool(tool)
        props = converted["function"]["parameters"]["properties"]

        assert props["str_param"]["type"] == "string"
        assert props["int_param"]["type"] == "integer"
        assert props["bool_param"]["type"] == "boolean"
        assert props["float_param"]["type"] == "number"


class TestAdapterCompatibility:
    """Test compatibility between different adapters."""

    @pytest.fixture
    def all_adapters(self):
        """Get all available adapters."""
        from titan_cli.tap.adapters.anthropic import AnthropicAdapter
        from titan_cli.tap.adapters.openai import OpenAIAdapter
        return {
            "anthropic": AnthropicAdapter,
            "openai": OpenAIAdapter
        }

    def test_all_adapters_convert_same_tool(self, all_adapters, sample_tools):
        """Test that all adapters can convert the same tool."""
        tool = sample_tools[0]  # read_file

        for name, adapter in all_adapters.items():
            converted = adapter.convert_tool(tool)
            assert converted is not None, f"{name} adapter failed to convert tool"

    def test_all_adapters_execute_same_tool(self, all_adapters, sample_tools):
        """Test that all adapters can execute the same tool."""
        tool_name = "calculator"
        tool_input = {"operation": "add", "a": 5, "b": 3}

        for name, adapter in all_adapters.items():
            result = adapter.execute_tool(tool_name, tool_input, sample_tools)
            assert result == 8, f"{name} adapter returned incorrect result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
