# Plan de Integración: Platform Agent + Agent Steps

## Objetivo

Integrar **PlatformAgent** (rama `feat/platform-agent`) con **Agent Steps** (rama `feat/workflow`) para crear un sistema unificado donde el mismo agente pueda usarse de dos formas:

1. **Interactive Mode** (TAP): Agente ejecuta tools autónomamente
2. **Analysis Mode** (Steps): Agente analiza datos pre-computados por workflows

## Estado Actual

### Rama `feat/platform-agent` (PR #26)
```
titan_cli/agents/
├── __init__.py
└── platform_agent.py         # PlatformAgent con TAP
    - run() → Ejecuta tools
    - get_tap_tools() → Retorna TitanTools
    - from_toml() → Carga config TOML
```

**Características:**
- ✅ Carga config TOML
- ✅ Integración TAP (AdapterManager)
- ✅ Tools: get_git_status, analyze_git_diff, create_commit
- ❌ No tiene modo analysis
- ❌ No se puede usar como workflow step

### Rama `feat/workflow` (PR #28) + Agent Steps
```
titan_cli/agents/steps/
├── __init__.py
└── analysis_step.py          # Agent steps genéricos
    - ai_analyze_changes_step()
    - ai_suggest_commit_message_step()
```

**Características:**
- ✅ Workflow steps que usan AI
- ✅ Analysis mode (no tool execution)
- ✅ Context-driven (lee ctx.data)
- ❌ No usa PlatformAgent
- ❌ No aprovecha config TOML del agent

## Plan de Integración

### Fase 1: Extender PlatformAgent con Analysis Mode

**Modificar `platform_agent.py`** para soportar dos modos:

```python
class PlatformAgent:
    """
    Platform agent con soporte dual mode:
    - Interactive: AI ejecuta tools (TAP)
    - Analysis: AI analiza datos (workflow step)
    """

    def run(
        self,
        ctx: WorkflowContext,
        user_context: str = "",
        mode: str = "interactive"  # ← NUEVO: "interactive" o "analysis"
    ) -> WorkflowResult:
        """
        Run agent in interactive or analysis mode.

        Args:
            ctx: Workflow context
            user_context: User instructions
            mode: "interactive" (with tools) or "analysis" (without tools)
        """
        if mode == "analysis":
            return self._run_analysis_mode(ctx, user_context)
        else:
            return self._run_interactive_mode(ctx, user_context)

    def _run_interactive_mode(
        self,
        ctx: WorkflowContext,
        user_context: str
    ) -> WorkflowResult:
        """
        Interactive mode: AI ejecuta tools (current behavior).
        """
        # Get TAP tools
        tools = self.get_tap_tools(ctx)

        # Get TAP adapter
        provider = self.config['tap']['provider']
        adapter_manager = AdapterManager.from_config("config/tap/adapters.toml")
        adapter = adapter_manager.get(provider)

        # Convert tools
        provider_tools = adapter.convert_tools(tools)

        # AI decides which tools to use
        response = ctx.ai.generate_with_tools(
            prompt=self.get_user_prompt(user_context),
            tools=provider_tools,
            system_prompt=self.get_system_prompt()
        )

        return Success(response, metadata={"mode": "interactive"})

    def _run_analysis_mode(
        self,
        ctx: WorkflowContext,
        user_context: str
    ) -> WorkflowResult:
        """
        Analysis mode: AI analiza datos de ctx.data (NO ejecuta tools).
        """
        # Extract data from context
        analysis_data = self._extract_context_data(ctx)

        if not analysis_data:
            from titan_cli.engine.results import Skip
            return Skip("No data in context to analyze")

        # Build analysis prompt
        prompt = self._build_analysis_prompt(analysis_data, user_context)

        # Get AI provider
        provider = self.config['tap']['provider']
        adapter_manager = AdapterManager.from_config("config/tap/adapters.toml")
        adapter = adapter_manager.get(provider)

        # Call AI WITHOUT tools (pure analysis)
        response = ctx.ai.generate(
            prompt=prompt,
            system_prompt=self._get_analysis_system_prompt()
        )

        return Success(
            response,
            metadata={
                "mode": "analysis",
                "data_keys": list(analysis_data.keys())
            }
        )

    def _extract_context_data(self, ctx: WorkflowContext) -> dict:
        """Extract relevant data from ctx.data for analysis."""
        data = {}

        # Git status
        if "git_status" in ctx.data:
            status = ctx.data["git_status"]
            data["git_status"] = {
                "branch": getattr(status, 'branch', ''),
                "modified": getattr(status, 'modified_files', []),
                "untracked": getattr(status, 'untracked_files', []),
                "is_clean": getattr(status, 'is_clean', False)
            }

        # Git diff
        if "git_diff" in ctx.data:
            data["git_diff"] = ctx.data["git_diff"]

        # Commit info
        if "commit_message" in ctx.data:
            data["commit_info"] = {
                "message": ctx.data["commit_message"],
                "hash": ctx.data.get("commit_hash")
            }

        return data

    def _build_analysis_prompt(self, data: dict, user_context: str) -> str:
        """Build analysis prompt from context data."""
        parts = []

        if user_context:
            parts.append(f"{user_context}\n\n")

        # Git status
        if "git_status" in data:
            status = data["git_status"]
            parts.append("## Repository Status\n\n")
            parts.append(f"- Branch: {status['branch']}\n")
            parts.append(f"- Modified: {len(status['modified'])} files\n")
            if status['modified']:
                for file in status['modified'][:10]:
                    parts.append(f"  - {file}\n")
            parts.append("\n")

        # Git diff
        if "git_diff" in data:
            parts.append(f"## Changes\n\n```diff\n{data['git_diff'][:2000]}\n```\n\n")

        return "".join(parts)

    def _get_analysis_system_prompt(self) -> str:
        """Get system prompt for analysis mode."""
        # Check if TOML has analysis-specific prompt
        if "analysis_system" in self.config.get("prompts", {}):
            return self.config["prompts"]["analysis_system"]

        # Fallback to regular system prompt
        return self.get_system_prompt()
```

### Fase 2: Crear Platform Agent Step Wrapper

**Nuevo archivo: `titan_cli/agents/steps/platform_agent_step.py`**

```python
"""
Platform Agent as Workflow Step

Wraps PlatformAgent to use it as a workflow step in analysis mode.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Skip
from titan_cli.agents.platform_agent import PlatformAgent
from typing import Optional


def platform_agent_analysis_step(
    ctx: WorkflowContext,
    agent_config: str = "config/agents/platform_agent.toml",
    task: Optional[str] = None
) -> WorkflowResult:
    """
    Run PlatformAgent in analysis mode as a workflow step.

    Reads from ctx.data (populated by previous steps) and uses
    PlatformAgent to analyze the data.

    Args:
        ctx: Workflow context
        agent_config: Path to agent TOML config
        task: Optional task description (uses TOML prompt if not provided)

    Returns:
        WorkflowResult from PlatformAgent

    Example:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,           # Populates ctx.data
            platform_agent_analysis_step   # Analyzes with PlatformAgent
        ])
    """

    # Check if AI is configured
    if not ctx.ai:
        return Skip("AI not configured")

    try:
        # Load PlatformAgent from TOML
        agent = PlatformAgent.from_toml(agent_config)

        # Get task from context or parameter
        user_context = ctx.data.get("agent_task") or task or ""

        # Run in analysis mode
        result = agent.run(
            ctx=ctx,
            user_context=user_context,
            mode="analysis"  # ← Analysis mode (no tools)
        )

        return result

    except FileNotFoundError:
        from titan_cli.engine.results import Error
        return Error(f"Agent config not found: {agent_config}")
    except Exception as e:
        from titan_cli.engine.results import Error
        return Error(f"Agent execution failed: {e}", exception=e)


def platform_agent_suggest_commit_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Specialized step: PlatformAgent suggests commit message.

    This is a convenience wrapper that:
    1. Runs PlatformAgent in analysis mode
    2. Extracts commit message from response
    3. Sets ctx.data["commit_message"] for next step

    Example:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,
            platform_agent_suggest_commit_step,  # ← Suggests commit
            create_git_commit_step               # ← Uses suggestion
        ])
    """

    # Check AI
    if not ctx.ai:
        return Skip("AI not configured")

    # Check data
    if ctx.data.get("git_status") and ctx.data["git_status"].is_clean:
        return Skip("Working directory is clean")

    try:
        agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")

        # Run analysis with specific task
        result = agent.run(
            ctx=ctx,
            user_context="Generate a conventional commit message for these changes",
            mode="analysis"
        )

        if result.success:
            # Extract commit message from AI response
            commit_msg = result.message.strip().strip('`').strip()

            from titan_cli.engine.results import Success
            return Success(
                f"Suggested: {commit_msg}",
                metadata={"commit_message": commit_msg}
            )
        else:
            return result

    except Exception as e:
        from titan_cli.engine.results import Error
        return Error(f"Failed to suggest commit: {e}", exception=e)
```

### Fase 3: Actualizar Configuración TOML

**Modificar `config/agents/platform_agent.toml`** para soportar ambos modos:

```toml
# Platform Agent Configuration
# Supports both interactive (TAP) and analysis modes

[agent]
name = "platform_agent"
description = "Platform engineering agent for Git, GitHub, and development workflows"
version = "1.0.0"

[tap]
provider = "anthropic"

# Tools for interactive mode
[[tap.tools]]
name = "get_git_status"
description = "Gets the current Git repository status"
enabled = true

[[tap.tools]]
name = "analyze_git_diff"
description = "Analyzes git diff to understand what changed"
enabled = true

[[tap.tools]]
name = "create_commit"
description = "Creates a Git commit with a conventional commit message"
enabled = true

[prompts]
# System prompt for interactive mode (with tools)
system = """
You are a Platform Engineering expert assistant.

Your role is to automate and streamline development workflows.

For Git commits, always use conventional commit format:
type(scope): description

WORKFLOW (Interactive Mode):
1. Use get_git_status to see what files have changed
2. Use analyze_git_diff to understand the nature of the changes
3. Use create_commit to create the commit with an appropriate message
"""

# System prompt for analysis mode (without tools)
analysis_system = """
You are a Platform Engineering expert analyzing Git changes.

Provide concise, actionable insights about:
- What changed and why
- Potential issues or concerns
- Recommendations

For commit suggestions, use conventional commit format:
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore
"""

user_template = """
Analyze the current Git changes and create appropriate commit(s).

Context: {context}
"""
```

### Fase 4: Workflow Examples

**Ejemplo 1: Análisis Simple**

```python
from titan_cli.engine import BaseWorkflow
from titan_plugin_git.steps import get_git_status_step
from titan_cli.agents.steps.platform_agent_step import platform_agent_analysis_step

workflow = BaseWorkflow(
    name="Platform Agent Analysis",
    steps=[
        get_git_status_step,           # Git plugin step
        platform_agent_analysis_step   # PlatformAgent in analysis mode
    ]
)
```

**Ejemplo 2: AI Commit con PlatformAgent**

```python
from titan_cli.agents.steps.platform_agent_step import (
    platform_agent_suggest_commit_step
)
from titan_plugin_git.steps import create_git_commit_step

workflow = BaseWorkflow(
    name="AI Commit (Platform Agent)",
    steps=[
        get_git_status_step,
        platform_agent_suggest_commit_step,  # Uses PlatformAgent
        create_git_commit_step
    ]
)
```

**Ejemplo 3: Dual Mode**

```python
# Same agent, different modes!

# Mode 1: Interactive (with tools)
agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
result = agent.run(ctx, mode="interactive")  # AI ejecuta tools

# Mode 2: Analysis (as workflow step)
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    platform_agent_analysis_step  # Same agent, analysis mode
])
result = workflow.run(ctx)
```

## Estructura de Archivos Final

```
titan_cli/agents/
├── __init__.py
├── platform_agent.py              # ← MODIFICAR: Añadir analysis mode
└── steps/
    ├── __init__.py
    ├── analysis_step.py           # Existing: Generic AI steps
    └── platform_agent_step.py     # ← NUEVO: PlatformAgent wrappers
```

## Ventajas de la Integración

### 1. Reutilización
- Mismo PlatformAgent, dos usos
- Misma config TOML, dos modos
- Mismo prompts, diferentes contextos

### 2. Consistencia
- Usa la misma configuración (platform_agent.toml)
- Usa el mismo TAP adapter
- Usa los mismos prompts

### 3. Flexibilidad
```python
# Opción 1: Interactive mode (autonomous)
agent.run(ctx, mode="interactive")

# Opción 2: Analysis mode (workflow step)
workflow = BaseWorkflow(steps=[..., platform_agent_analysis_step])

# Opción 3: Generic AI step (simple)
workflow = BaseWorkflow(steps=[..., ai_suggest_commit_message_step])
```

### 4. Evolución
- PlatformAgent puede crecer con más tools
- Tools se usan en interactive mode
- Analysis mode aprovecha el mismo contexto
- Config TOML centralizada

## Comparación

| Aspecto | Generic AI Steps | Platform Agent Steps |
|---------|------------------|----------------------|
| **Config** | Hardcoded prompts | TOML configurable |
| **Tools** | No usa tools | Puede usar tools (interactive) |
| **Reutilización** | Solo analysis | Interactive + Analysis |
| **Complejidad** | Simple | Más completo |
| **Use Case** | Quick AI tasks | Platform engineering |

## Migración

### Código Actual (Generic)
```python
from titan_cli.agents.steps import ai_suggest_commit_message_step

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step
])
```

### Código con PlatformAgent
```python
from titan_cli.agents.steps.platform_agent_step import (
    platform_agent_suggest_commit_step
)

workflow = BaseWorkflow(steps=[
    get_git_status_step,
    platform_agent_suggest_commit_step  # Usa config TOML
])
```

**Ambos siguen funcionando** - backward compatible.

## Tareas de Implementación

### En `feat/platform-agent`
- [ ] Añadir `mode` parameter a `PlatformAgent.run()`
- [ ] Implementar `_run_analysis_mode()`
- [ ] Implementar `_extract_context_data()`
- [ ] Implementar `_build_analysis_prompt()`
- [ ] Añadir `analysis_system` prompt en TOML
- [ ] Tests para analysis mode

### Nuevo Módulo
- [ ] Crear `titan_cli/agents/steps/platform_agent_step.py`
- [ ] Implementar `platform_agent_analysis_step()`
- [ ] Implementar `platform_agent_suggest_commit_step()`
- [ ] Tests para platform agent steps
- [ ] Actualizar `__init__.py` exports

### Documentación
- [ ] Actualizar `docs/PLATFORM_AGENT.md`
- [ ] Añadir sección "Dual Mode Usage"
- [ ] Ejemplos de workflow integration
- [ ] Migration guide

## Siguiente Paso

**¿Quieres que implemente esto en `feat/platform-agent`?**

Puedo:
1. Modificar `platform_agent.py` para añadir analysis mode
2. Crear `platform_agent_step.py` con los wrappers
3. Actualizar tests y documentación
4. Crear ejemplos de uso

Todo manteniend backward compatibility con el código existente.
