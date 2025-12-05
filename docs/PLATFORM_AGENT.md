# Platform Agent - TAP + TOML Implementation

**Platform Agent** is the simplest example of a TAP agent in Titan CLI.

## 🎯 Goals

Demonstrate:
1. **Pure TAP** - Zero coupling to frameworks
2. **TOML Configuration** - Configurable agent without code
3. **Autonomous AI** - AI decides which tools to use
4. **Reusability** - Uses existing Git workflow steps

## 📁 Files

```
titan-cli/
├── config/agents/
│   └── platform_agent.toml          # TOML Configuration
├── titan_cli/agents/
│   └── platform_agent.py             # Implementation
└── titan_cli/commands/
    └── agent.py                      # CLI command
```

## 🔧 Architecture

```
┌──────────────────────────────────────────┐
│  TOML Configuration                      │
│  - Tools enabled                         │
│  - System prompt                         │
│  - TAP provider                          │
└────────────┬─────────────────────────────┘
             │
             ↓
┌──────────────────────────────────────────┐
│  PlatformAgent.from_toml()               │
│  - Load config                           │
│  - Create TAP tools                      │
└────────────┬─────────────────────────────┘
             │
             ↓
┌──────────────────────────────────────────┐
│  TitanTools (TAP Protocol)               │
│  - GetGitStatusTool                      │
│  - AnalyzeGitDiffTool                    │
│  - CreateCommitTool                      │
└────────────┬─────────────────────────────┘
             │
             │ TAP Protocol
             ↓
┌──────────────────────────────────────────┐
│  TAP Adapter (from TOML config)          │
│  - anthropic / openai / langraph         │
│  - convert_tools()                       │
└────────────┬─────────────────────────────┘
             │
             ↓
┌──────────────────────────────────────────┐
│  AI Provider                             │
│  - Decide which tools to use             │
│  - Execute tools autonomously            │
└──────────────────────────────────────────┘
```

## 📋 TOML Configuration

[config/agents/platform_agent.toml](../config/agents/platform_agent.toml)

```toml
[agent]
name = "platform_agent"
description = "Platform engineering agent for Git, GitHub, and development workflows"
version = "1.0.0"

[tap]
provider = "anthropic"  # or: openai, langraph

[[tap.tools]]
name = "get_git_status"
description = "Gets Git repository status"
enabled = true

[[tap.tools]]
name = "analyze_git_diff"
description = "Analyzes git diff"
enabled = true

[[tap.tools]]
name = "create_commit"
description = "Creates a Git commit"
enabled = true

[prompts]
system = """
You are a Platform Engineering expert assistant.
Create well-structured conventional commits.
"""

user_template = """
Analyze the current Git changes and create commits.

Context: {context}
"""
```

### Flexible Configuration

You can create multiple TOML configs for different use cases:

```bash
config/agents/
├── platform_agent.toml           # Default
├── strict_commit_agent.toml      # Only conventional commits
├── auto_approve_agent.toml       # No confirmation
└── custom_provider_agent.toml    # OpenAI/LangGraph
```

## 🛠️ Implementation

### 1. PlatformAgent Class

[titan_cli/agents/platform_agent.py:PlatformAgent](../titan_cli/agents/platform_agent.py)

```python
class PlatformAgent:
    """Platform agent using TAP + TOML configuration."""

    def __init__(self, config: dict, config_path: Optional[Path] = None):
        self.config = config
        self.name = config['agent']['name']

    @classmethod
    def from_toml(cls, config_path: str | Path) -> 'PlatformAgent':
        """Load agent from TOML configuration file."""
        path = Path(config_path)
        with open(path, 'rb') as f:
            config = tomllib.load(f)
        return cls(config, path)

    def get_tap_tools(self, ctx: WorkflowContext) -> List[TitanTool]:
        """Get TAP tools defined in TOML configuration."""
        tools = []
        for tool_config in self.config['tap']['tools']:
            if tool_config.get('enabled', True):
                # Map tool names to implementations
                tool_name = tool_config['name']
                if tool_name == 'get_git_status':
                    tools.append(GetGitStatusTool(ctx.git))
                # ... more tools
        return tools

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        """Run the agent using TAP."""
        # 1. Get TAP tools from TOML config
        tools = self.get_tap_tools(ctx)

        # 2. Get TAP adapter (provider-agnostic)
        provider = self.config['tap']['provider']
        adapter_manager = AdapterManager.from_config("config/tap/adapters.toml")
        adapter = adapter_manager.get(provider)

        # 3. Convert tools to provider format
        provider_tools = adapter.convert_tools(tools)

        # 4. Get prompts from TOML
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt()

        # 5. AI decides which tools to use
        response = ctx.ai.generate_with_tools(
            prompt=user_prompt,
            tools=provider_tools,
            system_prompt=system_prompt
        )

        return Success("Agent execution completed")
```

**Key points:**
- ✅ Configuration-driven (TOML)
- ✅ TAP protocol (framework-agnostic)
- ✅ Provider-agnostic (Anthropic/OpenAI/LangGraph)
- ✅ Simple implementation (~150 lines)

### 2. TAP Tools

```python
class GetGitStatusTool(TitanTool):
    """TAP tool for getting Git status."""

    def __init__(self, git_client):
        schema = ToolSchema(
            name="get_git_status",
            description="Gets Git repository status",
            parameters={}
        )
        super().__init__(schema)
        self.git_client = git_client

    def execute(self) -> str:
        """Execute tool and return formatted status."""
        status = self.git_client.get_status()
        # Format and return
        return f"Branch: {status.branch}\n..."
```

Other tools:
- **AnalyzeGitDiffTool** - Analyzes changes with git diff
- **CreateCommitTool** - Creates conventional commits

## 🚀 Usage

### CLI Command

```bash
# Interactive mode
titan agent platform

# Auto-confirm
titan agent platform --yes

# Custom repo path
titan agent platform -p /path/to/repo

# Custom config
titan agent platform -c config/agents/custom.toml
```

### Execution Example

```
🤖 Platform Agent (TAP + TOML)
════════════════════════════════════════

Platform engineering agent with TOML configuration

📄 Loaded config: config/agents/platform_agent.toml
📦 Loaded 3 TAP tools
🔌 Using provider: anthropic

🧠 AI analyzing changes...

✅ Agent completed successfully!

📝 Execution Details:
Provider: anthropic
Tools available: 3
```

## 🎓 Comparison with Other Agents

| Feature | PlatformAgent | AutoCommitAgent | AutoCommitLangGraphAgent |
|---------|---------------|-----------------|--------------------------|
| **Complexity** | ⭐ Simple | ⭐⭐⭐ Medium | ⭐⭐⭐⭐⭐ High |
| **TOML Config** | ✅ Yes | ❌ No | ❌ No |
| **Cascade** | ❌ No | ✅ Yes (4 levels) | ✅ Yes (4 levels) |
| **Pure TAP** | ✅ Yes | ✅ Yes | ✅ Yes |
| **LangGraph** | ❌ No | ❌ No | ✅ Optional |
| **Token Opt** | ❌ No | ✅ Yes (77%) | ✅ Yes (77%) |
| **Use Case** | Demo/Learning | Production | Complex workflows |

## 📚 When to Use

### ✅ Use PlatformAgent when:
- **Learning** TAP and agent architecture
- **Prototyping** a new agent quickly
- **Need** flexible configuration without code
- **Want** to understand pure TAP without abstractions

### ❌ DON'T use PlatformAgent when:
- You need token optimization (use AutoCommitAgent)
- You need complex workflows (use AutoCommitLangGraphAgent)
- You need heuristics for simple cases
- It's critical production code

## 🔄 Evolution

### From PlatformAgent → AutoCommitAgent

If you need token optimization:

```python
# 1. Extend CascadeAgent instead of PlatformAgent
from titan_cli.agents.base_cascade_agent import CascadeAgent

class MyAgent(CascadeAgent):
    def try_heuristics(self) -> Optional[WorkflowResult]:
        # Add heuristic logic
        pass

    def get_tap_tools(self) -> List[TitanTool]:
        # Reuse tools from PlatformAgent
        return [GetGitStatusTool(), CreateCommitTool()]
```

### From PlatformAgent → Custom Agent

```python
# 1. Copy platform_agent.py
# 2. Modify tools in get_tap_tools()
# 3. Update TOML config
# 4. Add CLI command
```

## 💡 Best Practices

### 1. Separate Configuration from Code

✅ **Good**:
```toml
# config/agents/my_agent.toml
[prompts]
system = """
You are an expert in...
"""
```

❌ **Bad**:
```python
# Hardcoded in code
system_prompt = "You are an expert in..."
```

### 2. Reuse Existing Tools

✅ **Good**:
```python
# Reuse from existing agents
from titan_cli.agents.tools.git_tools import GetGitStatusTool
```

❌ **Bad**:
```python
# Duplicate tool implementation
class MyGetGitStatusTool(TitanTool): ...
```

### 3. Provider-Agnostic

✅ **Good**:
```toml
# Configurable in TOML
[tap]
provider = "anthropic"  # or openai, langraph
```

❌ **Bad**:
```python
# Hardcoded provider
from anthropic import Anthropic
client = Anthropic()
```

## 🧪 Testing

```python
# tests/agents/test_platform_agent.py

def test_load_from_toml():
    agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
    assert agent.name == "platform_agent"

def test_get_tap_tools():
    agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
    tools = agent.get_tap_tools(ctx)
    assert len(tools) == 3

def test_toml_config_validation():
    # Test invalid config
    with pytest.raises(ValidationError):
        PlatformAgent.from_toml("invalid.toml")
```

## 📖 References

- [TAP Architecture](./TAP_ARCHITECTURE.md) - Complete TAP architecture
- [Creating Agents](./CREATING_AGENTS.md) - Guide for creating agents (with Cascade)
- [Cascade Architecture](./CASCADE_ARCHITECTURE.md) - Token optimization

## ✅ Summary

**PlatformAgent** is the perfect starting point to understand:
- ✅ TAP protocol (framework-agnostic)
- ✅ TOML-based configuration
- ✅ AI autonomous tool selection
- ✅ Clean architecture

**Next steps:**
1. Try `titan agent platform`
2. Create your own `custom_agent.toml`
3. When you need token optimization → AutoCommitAgent
4. When you need complex workflows → LangGraph

---

**Simple. Configurable. Framework-agnostic.** 🚀
