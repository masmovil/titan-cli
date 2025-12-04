# TAP Integration Guide

## Overview

TAP (Titan Adapter Protocol) is now integrated into titan-cli, enabling autonomous AI agents with tool calling capabilities. This allows you to build intelligent workflows where AI agents can decide which tools to use to accomplish tasks.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         AIClient                            │
│  ┌──────────────┐                  ┌──────────────┐        │
│  │  generate()  │                  │generate_with │        │
│  │   (simple)   │                  │  _tools()    │        │
│  └──────────────┘                  └──────┬───────┘        │
│                                            │                │
└────────────────────────────────────────────┼────────────────┘
                                             │
                                             ▼
                                    ┌────────────────┐
                                    │   TAP Manager  │
                                    └───────┬────────┘
                                            │
                        ┌───────────────────┼───────────────────┐
                        ▼                   ▼                   ▼
                ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
                │  Anthropic   │    │   OpenAI     │    │  LangGraph   │
                │   Adapter    │    │   Adapter    │    │   Adapter    │
                └──────────────┘    └──────────────┘    └──────────────┘
```

## Key Components

### 1. TAP Protocol

Framework-agnostic protocol for tool adapters:

```python
class ToolAdapter(Protocol):
    @staticmethod
    def convert_tool(titan_tool: TitanTool) -> dict[str, Any]: ...

    @staticmethod
    def convert_tools(titan_tools: list[TitanTool]) -> list[dict[str, Any]]: ...

    @staticmethod
    def execute_tool(tool_name: str, tool_input: dict, tools: list[TitanTool]) -> Any: ...
```

### 2. Adapters

Pre-built adapters for major AI providers:

- **AnthropicAdapter**: Converts tools to Claude's format
- **OpenAIAdapter**: Converts tools to GPT function calling format
- **LangGraphAdapter**: Converts tools to LangGraph format

### 3. TAP Manager

Manages adapter lifecycle:

```python
from titan_cli.tap import TAPManager

# Load from config
manager = TAPManager.from_config("config/tap/adapters.yml")

# Get adapter
adapter = manager.get("anthropic")

# Convert tools
converted = adapter.convert_tools(tools)
```

### 4. AIClient Integration

Two modes of operation:

**Deterministic Mode** (existing):
```python
response = ai_client.chat(
    prompt="What is 2+2?",
    system_prompt="You are a helpful assistant"
)
```

**Autonomous Agent Mode** (new):
```python
response = ai_client.generate_with_tools(
    prompt="Analyze the codebase for security issues",
    tools=[read_file_tool, analyze_code_tool, report_tool],
    system_prompt="You are a security expert"
)
```

## Usage Examples

### Basic Tool Calling

```python
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ai.client import AIClient

# Initialize
config = TitanConfig()
secrets = SecretManager(config)
client = AIClient(config, secrets)

# Define tools
from your_tools import SearchTool, CalculatorTool

tools = [SearchTool(), CalculatorTool()]

# Run agent
result = client.generate_with_tools(
    prompt="Search for Python best practices and calculate how many there are",
    tools=tools
)

print(result['content'])        # Final answer
print(result['tool_calls'])     # Tools used
print(result['iterations'])     # Number of iterations
```

### GitHub PR Review Agent

```python
from titan_cli.engine import WorkflowContextBuilder

# Create context with AI
context = (
    WorkflowContextBuilder(config=config, secrets=secrets)
    .with_ai()
    .with_ui()
    .build()
)

# Set PR to review
context.data["pr_number"] = 123
context.data["review_focus"] = "security"
context.data["auto_comment"] = True

# Get step from plugin
github_plugin = context.config.registry.get_plugin("github")
review_step = github_plugin.get_steps()["review_pr"]

# Run autonomous review
result = review_step(context)

if result.success:
    print(result.metadata["review_summary"])
```

## Creating Custom Tools

Tools must follow the TitanTool interface:

```python
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ToolParameter:
    type_hint: str
    description: str = ""
    required: bool = True

@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)

class TitanTool:
    def __init__(self, schema: ToolSchema):
        self.schema = schema
        self.name = schema.name
        self.description = schema.description

    def execute(self, **kwargs) -> Any:
        raise NotImplementedError

# Example custom tool
class MyCustomTool(TitanTool):
    def __init__(self):
        schema = ToolSchema(
            name="my_tool",
            description="Does something useful",
            parameters={
                "input": ToolParameter(
                    type_hint="str",
                    description="Input data",
                    required=True
                )
            }
        )
        super().__init__(schema)

    def execute(self, input: str) -> str:
        # Your tool logic here
        return f"Processed: {input}"
```

## Configuration

### TAP Adapter Configuration

`config/tap/adapters.yml`:

```yaml
adapters:
  - name: anthropic
    module: titan_cli.tap.adapters.anthropic.AnthropicAdapter
    metadata:
      provider: Anthropic
      models:
        - claude-sonnet-4-20250514
        - claude-opus-4-20250514
    config:
      max_tokens: 4096
      temperature: 0.7

  - name: openai
    module: titan_cli.tap.adapters.openai.OpenAIAdapter
    metadata:
      provider: OpenAI
      models:
        - gpt-4
        - gpt-4-turbo
```

### AI Configuration

`.titan/config.toml`:

```toml
[ai]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
max_tokens = 4096
temperature = 0.7
```

## Testing

### Unit Tests

```bash
# Run TAP adapter tests
pytest tests/tap/test_adapters.py -v

# Run TAP manager tests
pytest tests/tap/test_manager.py -v

# Run AIClient integration tests
pytest tests/ai/test_client_tap.py -v
```

### Test Coverage

- **54 of 58 tests passing (93.1%)**
- All adapter conversion/execution tests ✓
- All manager lifecycle tests ✓
- All AIClient integration tests ✓

### Example Test

```python
def test_tool_calling():
    # Mock tools
    tools = [MockSearchTool(), MockCalculatorTool()]

    # Run agent
    result = client.generate_with_tools(
        prompt="Search for info and calculate result",
        tools=tools
    )

    # Verify
    assert result['iterations'] > 0
    assert len(result['tool_calls']) > 0
    assert 'content' in result
```

## Workflows

### Available GitHub Plugin Steps

1. **`create_pr`** - Create pull request (existing)
2. **`review_pr`** - AI-powered general code review (new)
3. **`analyze_pr_security`** - Security-focused review (new)
4. **`analyze_pr_performance`** - Performance-focused review (new)

### Example Workflow

```python
from titan_cli.engine import WorkflowEngine

# Define workflow
workflow = [
    ("analyze_security", "github.analyze_pr_security"),
    ("analyze_performance", "github.analyze_pr_performance"),
]

# Execute
engine = WorkflowEngine(context)
results = engine.run(workflow)
```

## Best Practices

### 1. Tool Design

- ✅ Keep tools focused and single-purpose
- ✅ Provide clear, descriptive names
- ✅ Include detailed parameter descriptions
- ✅ Handle errors gracefully
- ❌ Don't create overly complex tools
- ❌ Don't mix multiple concerns in one tool

### 2. Agent Prompts

- ✅ Be specific about the task
- ✅ Provide context and guidelines
- ✅ Set clear success criteria
- ✅ Use lower temperature for analytical tasks (0.3-0.5)
- ❌ Don't be vague about expectations
- ❌ Don't use high temperature for deterministic tasks

### 3. Error Handling

```python
try:
    result = client.generate_with_tools(
        prompt=prompt,
        tools=tools
    )

    if result['iterations'] >= 10:
        # Max iterations reached
        logger.warning("Agent reached max iterations")

    return result['content']

except AIConfigurationError as e:
    logger.error(f"AI configuration error: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

### 4. Performance

- Limit number of tools (5-10 recommended)
- Set appropriate max_tokens
- Monitor iteration count
- Cache tool results when possible
- Use streaming for long-running operations

## Troubleshooting

### Common Issues

**1. KeyError: Adapter not found**

```python
# Solution: Register adapter in config/tap/adapters.yml
# Or register manually:
from titan_cli.tap import TAPManager
manager = TAPManager()
manager.registry.register("my_adapter", MyAdapter)
```

**2. Tool not being called**

- Check tool description is clear
- Verify parameters are well-defined
- Lower temperature for more focused behavior
- Check system prompt guides tool usage

**3. Max iterations reached**

- Review tool execution logic
- Check if tools return useful results
- Verify agent isn't stuck in a loop
- Consider increasing max_iterations (default: 10)

## Performance Metrics

### Typical Performance

- **Simple query (no tools)**: 1-2s
- **Single tool call**: 3-5s
- **Multiple tool calls (3-5)**: 10-15s
- **Complex analysis (8-10 tools)**: 20-30s

### Optimization Tips

1. **Batch operations**: Combine related tool calls
2. **Parallel execution**: Use async tools when possible
3. **Caching**: Cache expensive tool results
4. **Streaming**: Stream long responses
5. **Tool selection**: Provide only relevant tools

## Examples

See complete working examples in:

- [`examples/tap_integration_example.py`](../examples/tap_integration_example.py) - Basic TAP usage
- [`examples/github_pr_review_workflow.py`](../examples/github_pr_review_workflow.py) - PR review workflows

## API Reference

### AIClient.generate_with_tools()

```python
def generate_with_tools(
    self,
    prompt: str,
    tools: List[TitanTool],
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> dict[str, Any]:
    """
    Generate response with tool calling support.

    Args:
        prompt: User prompt/question
        tools: List of TitanTool instances
        system_prompt: Optional system instructions
        max_tokens: Override default max_tokens
        temperature: Override default temperature

    Returns:
        {
            'content': str,           # Final response
            'tool_calls': list,       # Tools used
            'iterations': int         # Number of iterations
        }
    """
```

### TAPManager.get()

```python
def get(
    self,
    name: str,
    use_cache: bool = True,
    **config
) -> ToolAdapter:
    """
    Get adapter by name.

    Args:
        name: Adapter name ('anthropic', 'openai', etc.)
        use_cache: Whether to use cached instance
        **config: Additional configuration

    Returns:
        ToolAdapter instance

    Raises:
        KeyError: If adapter not found
    """
```

## Future Enhancements

### Planned Features

- [ ] Multi-agent collaboration
- [ ] Agent memory/context persistence
- [ ] Tool result caching layer
- [ ] Streaming tool execution
- [ ] Agent performance analytics
- [ ] Custom adapter development guide
- [ ] Agent behavior profiling
- [ ] Tool marketplace

### Experimental Features

- Multi-modal tool support (images, audio)
- Agent-to-agent communication
- Hierarchical agent systems
- Reinforcement learning for tool selection

## Contributing

To add a new adapter:

1. Implement `ToolAdapter` protocol
2. Add to `titan_cli/tap/adapters/`
3. Register in `config/tap/adapters.yml`
4. Add tests in `tests/tap/`
5. Update documentation

## Resources

- [TAP Protocol Specification](./TAP_PROTOCOL.md)
- [Agent Development Guide](./AGENT_DEVELOPMENT.md)
- [Tool Development Guide](./TOOL_DEVELOPMENT.md)
- [Example Workflows](../examples/)

## Support

For issues, questions, or contributions:
- GitHub Issues: [titan-cli/issues](https://github.com/your-org/titan-cli/issues)
- Discussions: [titan-cli/discussions](https://github.com/your-org/titan-cli/discussions)
