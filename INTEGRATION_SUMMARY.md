# Integración de Agent Steps en feat/workflow

## Resumen

Se ha integrado la funcionalidad de **Agent Steps** en la rama `feat/workflow`, permitiendo usar agentes AI como workflow steps regulares.

## Archivos Creados

### 1. Core Implementation
```
titan_cli/agents/steps/
├── __init__.py
└── analysis_step.py  (246 líneas)
```

**Contenido:**
- `ai_analyze_changes_step()` - Analiza cambios git con AI
- `ai_suggest_commit_message_step()` - Genera commit messages con AI
- Helper functions para build prompts

### 2. Examples
```
examples/workflows/
└── ai_commit_workflow.py  (179 líneas)
```

**Contenido:**
- `create_ai_commit_workflow()` - Workflow completamente automatizado
- `create_hybrid_commit_workflow()` - AI sugiere, usuario confirma
- Ejemplo de CLI command

### 3. Tests
```
tests/agents/steps/
└── test_analysis_step.py  (166 líneas)
```

**Contenido:**
- 13 tests para `ai_analyze_changes_step`
- 7 tests para `ai_suggest_commit_message_step`
- Tests para skip conditions, errors, success cases

### 4. Documentation
```
docs/
└── AGENT_STEPS.md  (395 líneas)
```

**Contenido:**
- Conceptos y arquitectura
- API reference para cada step
- Patrones de uso (automated, hybrid, analysis)
- Best practices
- Testing guide

## Concepto Central

### Agent Steps = Workflow Steps con AI

```python
# Traditional step (manual)
def prompt_for_commit_message_step(ctx):
    message = ctx.views.prompts.ask_text("Enter message:")
    return Success(metadata={"commit_message": message})

# Agent step (AI-powered)
def ai_suggest_commit_message_step(ctx):
    # Lee datos de ctx.data (populated por steps previos)
    git_status = ctx.data["git_status"]

    # Genera mensaje con AI (sin ejecutar tools)
    message = ctx.ai.generate(prompt, system_prompt)

    # Retorna resultado
    return Success(metadata={"commit_message": message})
```

## Integración con Workflow Existente

Los agent steps se integran perfectamente con steps existentes:

```python
from titan_cli.engine import BaseWorkflow
from titan_plugin_git.steps import get_git_status_step, create_git_commit_step
from titan_cli.agents.steps import ai_suggest_commit_message_step

workflow = BaseWorkflow(
    name="AI Commit",
    steps=[
        get_git_status_step,           # Step existente (Git plugin)
        ai_suggest_commit_message_step, # ← NUEVO: Agent step
        create_git_commit_step          # Step existente (Git plugin)
    ]
)
```

## Características Clave

### 1. Analysis Mode
- **NO ejecuta tools** (a diferencia de agentes interactivos TAP)
- **Solo analiza** datos pre-computados
- **Lower token usage** (sin tool calling loops)

### 2. Context-Driven
- Lee `ctx.data` poblado por steps anteriores
- Escribe resultados a `ctx.data`
- Sigue el patrón estándar de workflow steps

### 3. Graceful Degradation
- **Auto-skip** si AI no configurado
- **Auto-skip** si no hay datos
- **Fallback** a steps manuales si falla

### 4. Testeable
- Mocks simples de `ctx.ai`
- Sin dependencias externas
- Tests rápidos

## Flujo de Datos

```
Step 1: get_git_status_step
    ↓ ctx.data["git_status"] = GitStatus(...)

Step 2: ai_suggest_commit_message_step
    ↓ Lee ctx.data["git_status"]
    ↓ Llama ctx.ai.generate(...)
    ↓ ctx.data["commit_message"] = "feat: add feature"

Step 3: create_git_commit_step
    ↓ Lee ctx.data["commit_message"]
    ↓ Ejecuta git commit
```

## Patrones de Uso

### Patrón 1: Fully Automated
```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step,
    create_git_commit_step,
    push_step
])
# ✅ Zero user interaction
```

### Patrón 2: AI-Assisted (Hybrid)
```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_suggest_commit_message_step,  # AI suggests
    prompt_with_ai_suggestion_step,  # User confirms/modifies
    create_git_commit_step
])
# ✅ Best of both worlds
```

### Patrón 3: Analysis + Insights
```python
workflow = BaseWorkflow(steps=[
    get_git_status_step,
    ai_analyze_changes_step,         # Get insights
    ai_suggest_commit_message_step,  # Get commit msg
    create_git_commit_step
])
# ✅ Rich context + automation
```

## Compatibilidad

### ✅ Compatible con:
- Workflow system existente (`BaseWorkflow`)
- Git plugin steps (`get_git_status_step`, `create_git_commit_step`)
- GitHub plugin steps (futuro)
- WorkflowResult (Success, Error, Skip)
- WorkflowContext + ctx.data

### ✅ No Rompe:
- Workflows existentes (agent steps son opcionales)
- Steps existentes (no hay cambios)
- Tests existentes (agent steps aislados)

## Ventajas vs Agentes Interactivos

| Aspecto | Agent Steps | Interactive Agents (TAP) |
|---------|-------------|--------------------------|
| **Complejidad** | Simple | Compleja |
| **Token Usage** | Bajo | Alto (tool loops) |
| **Tool Execution** | No | Sí |
| **Integration** | Drop-in workflow step | Custom integration |
| **Testing** | Fácil (mock AI) | Complejo (mock tools) |
| **Use Case** | Analyze, suggest | Execute, create |

## Próximos Pasos

### Corto Plazo (Esta PR)
1. Revisar implementación
2. Ejecutar tests
3. Validar con workflow real
4. Mergear a feat/workflow

### Medio Plazo
1. Integrar con PR #26 (PlatformAgent)
2. Añadir más agent steps:
   - `ai_review_pr_step`
   - `ai_categorize_changes_step`
   - `ai_estimate_risk_step`

### Largo Plazo
1. Configuración TOML para agent steps
2. Métricas de token usage
3. Cache de AI responses
4. Multi-provider support (OpenAI, etc.)

## Testing

### Run Tests
```bash
# All agent step tests
pytest tests/agents/steps/ -v

# Specific test
pytest tests/agents/steps/test_analysis_step.py::TestAISuggestCommitMessageStep -v

# With coverage
pytest tests/agents/steps/ --cov=titan_cli.agents.steps --cov-report=term-missing
```

### Expected Results
- 20 tests total
- All passing
- ~90%+ coverage

## Ejemplo de Uso Real

```bash
# 1. Configure AI
titan ai configure

# 2. Create workflow file (or use example)
cp examples/workflows/ai_commit_workflow.py my_workflow.py

# 3. Run workflow
python my_workflow.py

# Output:
# 🤖 AI suggested commit message:
#    feat(docs): add agent steps documentation
# ✅ Commit created successfully!
```

## Conclusión

La integración de **Agent Steps** permite:
- ✅ Usar AI en workflows de forma simple y natural
- ✅ Mantener compatibilidad con sistema existente
- ✅ Ofrecer múltiples patrones de uso (automated/hybrid/analysis)
- ✅ Testing y mantenimiento fácil
- ✅ Evolución futura (más agent steps, configuración TOML, etc.)

**Sin romper nada existente** ✨
