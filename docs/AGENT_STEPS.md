# Agent Steps: AI-Powered Workflow Steps

Agent Steps integrate AI agents into workflows as regular workflow steps. Unlike interactive agents that execute tools, agent steps run in **analysis mode** - they receive pre-computed data from previous steps and provide AI-powered insights.

## Concept

```
Traditional Workflow           AI-Enhanced Workflow
─────────────────────         ───────────────────────
get_git_status_step           get_git_status_step
        ↓                             ↓
prompt_for_commit_message     ai_suggest_commit_message_step  ← AI Agent
        ↓                             ↓
create_git_commit_step        create_git_commit_step
```

## Available Agent Steps

### 1. `ai_analyze_changes_step`

Analyzes git changes and provides insights.

**Reads from `ctx.data`:**
- `git_status` (from `get_git_status_step`)
- `git_diff` (optional)
- `analysis_prompt` (optional custom prompt)

**Writes to `ctx.data`:**
- `ai_analysis` - Analysis text from AI

**Returns:**
- `Success` - Analysis completed
- `Skip` - No AI, no data, or clean working directory
- `Error` - AI generation failed

**Example:**
```python
from titan_cli.engine import BaseWorkflow
from titan_plugin_git.steps import get_git_status_step
from titan_cli.agents.steps import ai_analyze_changes_step

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_analyze_changes_step
])

result = workflow.run(ctx)
analysis = result.metadata["ai_analysis"]
```

### 2. `ai_suggest_commit_message_step`

Generates conventional commit messages using AI.

**Reads from `ctx.data`:**
- `git_status` (required)
- `git_diff` (optional, improves accuracy)
- `commit_type_hint` (optional: "feat", "fix", etc.)

**Writes to `ctx.data`:**
- `suggested_commit_message` - AI-generated message
- `commit_message` - Same as above (auto-populated for next step)

**Returns:**
- `Success` - Message generated
- `Skip` - No AI, clean directory, or no data
- `Error` - Generation failed

**Example:**
```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step,  # Generates commit message
    create_git_commit_step            # Uses the generated message
])
```

## Usage Patterns

### Pattern 1: Fully Automated Commits

AI generates commit message, workflow commits automatically.

```python
from titan_cli.engine import BaseWorkflow
from titan_plugin_git.steps import get_git_status_step, create_git_commit_step
from titan_plugin_git.steps.push_step import push_step
from titan_cli.agents.steps import ai_suggest_commit_message_step

workflow = BaseWorkflow(
    name="AI Auto-Commit",
    steps=[
        get_git_status_step,
        ai_suggest_commit_message_step,
        create_git_commit_step,
        push_step
    ]
)
```

### Pattern 2: AI Suggests, User Confirms

AI generates suggestion, user can accept or modify.

```python
def prompt_with_ai_suggestion_step(ctx):
    """Show AI suggestion and let user modify it."""
    suggested = ctx.data.get("suggested_commit_message")

    if suggested:
        print(f"🤖 AI suggests: {suggested}")
        if ctx.views.prompts.ask_confirm("Use this message?"):
            return Success(metadata={"commit_message": suggested})

    # User wants to modify
    return prompt_for_commit_message_step(ctx)

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step,
    prompt_with_ai_suggestion_step,  # User confirms/modifies
    create_git_commit_step
])
```

### Pattern 3: Analysis + Action

Get AI insights before committing.

```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_analyze_changes_step,          # Get insights
    ai_suggest_commit_message_step,   # Get commit message
    create_git_commit_step
])

result = workflow.run(ctx)

# Access insights
print(result.metadata["ai_analysis"])
print(result.metadata["suggested_commit_message"])
```

## Customization

### Custom Analysis Prompt

```python
# Before running workflow, set custom prompt
ctx.data["analysis_prompt"] = """
Analyze these changes for:
1. Security vulnerabilities
2. Performance impact
3. Breaking changes
"""

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_analyze_changes_step
])
```

### Commit Type Hints

```python
# Hint the AI about commit type
ctx.data["commit_type_hint"] = "fix"

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step  # Will prefer "fix:" type
])
```

### Custom System Prompts

```python
ctx.data["analysis_system_prompt"] = """
You are a senior code reviewer.
Focus on architectural concerns and best practices.
"""

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_analyze_changes_step
])
```

## How It Works

### Data Flow

```
Step 1: get_git_status_step
    ↓ writes ctx.data["git_status"]

Step 2: ai_suggest_commit_message_step
    ↓ reads ctx.data["git_status"]
    ↓ calls ctx.ai.generate(prompt, system_prompt)
    ↓ writes ctx.data["commit_message"]

Step 3: create_git_commit_step
    ↓ reads ctx.data["commit_message"]
    ↓ creates commit
```

### Analysis Mode vs Interactive Mode

| Aspect | Agent Steps (Analysis) | Interactive Agents (TAP) |
|--------|------------------------|--------------------------|
| **Tool Execution** | ❌ No tools | ✅ AI decides which tools |
| **Input** | Pre-computed data | Live environment |
| **Output** | Text analysis | Actions + results |
| **Use Case** | Analyze, suggest, review | Execute, create, modify |
| **Token Usage** | Lower (no tool calls) | Higher (tool execution loops) |

## Best Practices

### 1. Provide Rich Context

More data = better AI suggestions:

```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,          # ← Provides status
    get_git_diff_step,            # ← Provides diff (if available)
    get_branch_info_step,         # ← Provides branch context
    ai_suggest_commit_message_step
])
```

### 2. Handle Failures Gracefully

```python
result = workflow.run(ctx)

if result.success:
    commit_msg = result.metadata.get("suggested_commit_message")
else:
    # Fallback to manual prompt
    commit_msg = ctx.views.prompts.ask_text("Enter commit message:")
```

### 3. Skip When Appropriate

Agent steps automatically skip when:
- AI not configured
- No data to analyze
- Working directory is clean

```python
# This workflow gracefully skips AI if not configured
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step,  # Skips if no AI
    prompt_for_commit_message_step,  # Fallback to manual
    create_git_commit_step
])
```

## Testing

Agent steps are unit tested with mocked AI:

```python
def test_ai_suggest_commit():
    ctx = WorkflowContext()

    # Mock AI
    ctx.ai = Mock()
    ctx.ai.generate = Mock(return_value="feat: add feature")

    # Mock git status
    git_status = Mock(is_clean=False, modified_files=["file.py"])
    ctx.data = {"git_status": git_status}

    result = ai_suggest_commit_message_step(ctx)

    assert result.success
    assert result.metadata["commit_message"] == "feat: add feature"
```

## Architecture

Agent steps follow the **3-Layer Architecture**:

```
Layer 1: Core Operations
    ↓
Layer 2: Workflow Steps (Agent Steps = Layer 2)
    ↓
Layer 3: Workflows
```

Agent steps are **Layer 2 adapters** that:
1. Read data from `ctx.data` (populated by other Layer 2 steps)
2. Call AI for analysis (no tools)
3. Write results back to `ctx.data`

## Migration from Interactive Agents

If you have an interactive agent:

```python
# Before: Interactive agent (executes tools)
agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
result = agent.run(ctx, user_context="Analyze changes")
```

Convert to agent step:

```python
# After: Agent step (analysis only)
workflow = BaseWorkflow(steps=[
    get_git_status_step,           # Provide data
    ai_analyze_changes_step        # Agent analyzes (no tools)
])
result = workflow.run(ctx)
```

## Future Enhancements

Potential future agent steps:

- `ai_review_pr_step` - Reviews PR for issues
- `ai_suggest_improvements_step` - Code improvement suggestions
- `ai_categorize_changes_step` - Groups changes by module/type
- `ai_estimate_risk_step` - Rates change risk level
- `ai_generate_changelog_step` - Creates changelog entries

---

**See also:**
- [Workflow Engine Documentation](./WORKFLOW_ENGINE.md)
- [TAP Architecture](./TAP_ARCHITECTURE.md)
- [Creating Agents](./CREATING_AGENTS.md)
