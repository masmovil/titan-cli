"""
Tests for AIClient TAP integration.

Tests the generate_with_tools() method and tool calling functionality.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import tempfile
from typing import Any, Dict
from dataclasses import dataclass, field

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError


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


# Mock tools for testing
class MockSearchTool(TitanTool):
    """Mock search tool."""

    def __init__(self):
        schema = ToolSchema(
            name="search",
            description="Searches for information",
            parameters={
                "query": ToolParameter(
                    type_hint="str",
                    description="Search query",
                    required=True
                )
            }
        )
        super().__init__(schema)

    def execute(self, query: str) -> str:
        """Execute search."""
        return f"Search results for: {query}"


class MockCalculatorTool(TitanTool):
    """Mock calculator tool."""

    def __init__(self):
        schema = ToolSchema(
            name="calculator",
            description="Performs calculations",
            parameters={
                "expression": ToolParameter(
                    type_hint="str",
                    description="Mathematical expression",
                    required=True
                )
            }
        )
        super().__init__(schema)

    def execute(self, expression: str) -> str:
        """Execute calculation."""
        try:
            result = eval(expression)
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {str(e)}"


@pytest.fixture
def temp_config():
    """Create temporary config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".titan"
        config_dir.mkdir(parents=True)

        # Create minimal config
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[ai]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
max_tokens = 4096
temperature = 0.7
""")

        # Create TAP config
        tap_config_dir = Path(tmpdir) / "config" / "tap"
        tap_config_dir.mkdir(parents=True)
        tap_config_file = tap_config_dir / "adapters.yml"
        tap_config_file.write_text("""
adapters:
  - name: anthropic
    module: titan_cli.tap.adapters.anthropic.AnthropicAdapter
    metadata:
      provider: Anthropic
      models:
        - claude-sonnet-4-20250514
""")

        yield config_file, tap_config_file


@pytest.fixture
def mock_secrets():
    """Create mock SecretManager."""
    secrets = Mock(spec=SecretManager)
    secrets.get.return_value = "test_api_key"
    return secrets


@pytest.fixture
def sample_tools():
    """Create sample tools."""
    return [MockSearchTool(), MockCalculatorTool()]


class TestAIClientTAPInitialization:
    """Tests for AIClient TAP initialization."""

    def test_tap_property_lazy_loading(self, temp_config, mock_secrets):
        """Test that TAP manager is lazy loaded."""
        config_file, tap_config = temp_config

        # Patch the tap config path resolution
        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            # TAP should not be loaded yet
            assert client._tap_manager is None

            # Access TAP property
            tap = client.tap

            # Now it should be loaded
            assert tap is not None
            assert client._tap_manager is not None

    def test_tap_configuration_error_missing_ai_config(self, mock_secrets):
        """Test error when AI config is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".titan"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.toml"
            config_file.write_text("")  # Empty config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            with pytest.raises(AIConfigurationError, match="AI configuration section is missing"):
                _ = client.tap

    def test_tap_configuration_error_missing_api_key(self, temp_config):
        """Test error when API key is missing."""
        config_file, _ = temp_config

        secrets = Mock(spec=SecretManager)
        secrets.get.return_value = None  # No API key

        titan_config = TitanConfig(config_file.parent.parent)
        client = AIClient(titan_config, secrets)

        with pytest.raises(AIConfigurationError, match="API key .* not found"):
            _ = client.tap


class TestGenerateWithTools:
    """Tests for generate_with_tools method."""

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_basic(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test basic tool calling workflow."""
        config_file, tap_config = temp_config

        # Mock Anthropic response (no tools used, direct answer)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="The answer is 42")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        # Patch path resolution
        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config  # Make exists() check pass

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            result = client.generate_with_tools(
                prompt="What is the answer?",
                tools=sample_tools
            )

            assert result["content"] == "The answer is 42"
            assert result["tool_calls"] == []
            assert result["iterations"] == 1

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_single_tool_call(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test workflow with single tool call."""
        config_file, tap_config = temp_config

        # Mock Anthropic responses
        # First response: AI wants to use calculator tool
        tool_use_response = MagicMock()
        tool_use_response.stop_reason = "tool_use"
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "calculator"
        tool_use_block.input = {"expression": "2 + 2"}
        tool_use_block.id = "tool_123"
        tool_use_response.content = [tool_use_block]

        # Second response: AI provides final answer
        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [MagicMock(text="The result of 2 + 2 is 4")]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [tool_use_response, final_response]
        mock_anthropic_class.return_value = mock_client

        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            result = client.generate_with_tools(
                prompt="What is 2 + 2?",
                tools=sample_tools
            )

            assert "The result" in result["content"]
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["tool"] == "calculator"
            assert result["tool_calls"][0]["input"] == {"expression": "2 + 2"}
            assert "Result: 4" in result["tool_calls"][0]["output"]
            assert result["iterations"] == 2

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_multiple_iterations(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test workflow with multiple tool calls."""
        config_file, tap_config = temp_config

        # First tool call
        tool_use_1 = MagicMock()
        tool_use_1.stop_reason = "tool_use"
        block_1 = MagicMock()
        block_1.type = "tool_use"
        block_1.name = "search"
        block_1.input = {"query": "Python"}
        block_1.id = "tool_1"
        tool_use_1.content = [block_1]

        # Second tool call
        tool_use_2 = MagicMock()
        tool_use_2.stop_reason = "tool_use"
        block_2 = MagicMock()
        block_2.type = "tool_use"
        block_2.name = "calculator"
        block_2.input = {"expression": "10 * 10"}
        block_2.id = "tool_2"
        tool_use_2.content = [block_2]

        # Final response
        final = MagicMock()
        final.stop_reason = "end_turn"
        final.content = [MagicMock(text="Based on the search and calculation, here's your answer")]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [tool_use_1, tool_use_2, final]
        mock_anthropic_class.return_value = mock_client

        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            result = client.generate_with_tools(
                prompt="Search for Python and calculate 10 * 10",
                tools=sample_tools
            )

            assert len(result["tool_calls"]) == 2
            assert result["tool_calls"][0]["tool"] == "search"
            assert result["tool_calls"][1]["tool"] == "calculator"
            assert result["iterations"] == 3

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_max_iterations(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test that max iterations limit is enforced."""
        config_file, tap_config = temp_config

        # Always return tool_use to trigger max iterations
        tool_use = MagicMock()
        tool_use.stop_reason = "tool_use"
        block = MagicMock()
        block.type = "tool_use"
        block.name = "search"
        block.input = {"query": "test"}
        block.id = "tool_x"
        tool_use.content = [block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = tool_use
        mock_anthropic_class.return_value = mock_client

        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            result = client.generate_with_tools(
                prompt="Keep searching",
                tools=sample_tools
            )

            assert result["iterations"] == 10  # Max iterations
            assert result["content"] == "Max iterations reached"
            assert len(result["tool_calls"]) == 10

    def test_generate_with_tools_unsupported_provider(self, temp_config, mock_secrets, sample_tools):
        """Test error with unsupported provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".titan"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.toml"
            config_file.write_text("""
[ai]
provider = "gemini"
model = "gemini-pro"
max_tokens = 4096
temperature = 0.7
""")

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            with pytest.raises(AIConfigurationError, match="Tool calling not supported for provider"):
                client.generate_with_tools(
                    prompt="Test",
                    tools=sample_tools
                )

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_with_system_prompt(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test that system prompt is included."""
        config_file, tap_config = temp_config

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Response")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            client.generate_with_tools(
                prompt="Test",
                tools=sample_tools,
                system_prompt="You are a helpful assistant"
            )

            # Check that messages include system prompt
            call_kwargs = mock_client.messages.create.call_args.kwargs
            messages = call_kwargs["messages"]
            assert any(msg.get("role") == "system" for msg in messages)

    @patch('anthropic.Anthropic')
    def test_generate_with_tools_parameters_override(self, mock_anthropic_class, temp_config, mock_secrets, sample_tools):
        """Test that max_tokens and temperature can be overridden."""
        config_file, tap_config = temp_config

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text="Response")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch('titan_cli.ai.client.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tap_config.parent.parent
            mock_path.return_value = tap_config

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            client.generate_with_tools(
                prompt="Test",
                tools=sample_tools,
                max_tokens=2000,
                temperature=0.5
            )

            # Check that custom params were used
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 2000
            assert call_kwargs["temperature"] == 0.5


class TestOpenAIToolCalling:
    """Tests for OpenAI tool calling (stub)."""

    def test_openai_tool_calling_not_implemented(self, temp_config, mock_secrets, sample_tools):
        """Test that OpenAI tool calling raises NotImplementedError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".titan"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.toml"
            config_file.write_text("""
[ai]
provider = "openai"
model = "gpt-4"
max_tokens = 4096
temperature = 0.7
""")

            titan_config = TitanConfig(config_file.parent.parent)
            client = AIClient(titan_config, mock_secrets)

            with pytest.raises(NotImplementedError, match="OpenAI tool calling not yet implemented"):
                client.generate_with_tools(
                    prompt="Test",
                    tools=sample_tools
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
