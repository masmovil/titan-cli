# Menu AI PR Implementation

## 🎯 Objetivo
Agregar una opción en el menú interactivo de Titan CLI para crear Pull Requests con IA habilitada.

## ✅ Implementación Completada

### 1. **WorkflowExecutor - Soporte para Parámetros Override**
**Archivo**: [titan_cli/engine/workflow_executor.py](titan_cli/engine/workflow_executor.py:24-42)

**Cambios**:
- Modificado método `execute()` para aceptar parámetro opcional `params_override`
- Los workflow params se cargan automáticamente en `ctx.data`
- Los parámetros override tienen prioridad sobre los defaults del workflow

```python
def execute(self, workflow: ParsedWorkflow, ctx: WorkflowContext, params_override: Optional[Dict[str, Any]] = None) -> WorkflowResult:
    # Merge workflow params into ctx.data with optional overrides
    effective_params = {**workflow.params}
    if params_override:
        effective_params.update(params_override)

    # Load params into ctx.data so steps can access them
    ctx.data.update(effective_params)
    # ...
```

**Beneficio**: Permite ejecutar el mismo workflow con diferentes parámetros desde el código.

### 2. **CLI Menu - Nueva Opción "Create PR with AI"**
**Archivo**: [titan_cli/cli.py](titan_cli/cli.py:144-146)

**Cambios en el Menú**:
```python
menu_builder.add_category("Workflows", emoji="⚡") \
    .add_item("Run a Workflow", "Execute a predefined or custom workflow.", "run_workflow") \
    .add_item("Create PR with AI", "Create a GitHub Pull Request using AI to generate description.", "create_pr_with_ai")
```

**Handler Implementado**: [titan_cli/cli.py](titan_cli/cli.py:292-357)

```python
elif choice_action == "create_pr_with_ai":
    text.title("Create Pull Request with AI")
    spacer.line()

    # Check if AI is configured
    config.load()
    if not config.config.ai:
        text.error("AI is not configured. Please run 'Configure AI Provider' first.")
        continue

    # Execute workflow with use_ai=true override
    executor.execute(parsed_workflow, execution_context, params_override={"use_ai": True})
```

**Características**:
- ✅ Verifica que IA esté configurada antes de ejecutar
- ✅ Ejecuta automáticamente el workflow "Create Pull Request" con `use_ai=true`
- ✅ Muestra errores claros si falta configuración
- ✅ Retorna al menú principal después de ejecutar

## 📁 Archivos Modificados

### 1. WorkflowExecutor
**Archivo**: `titan_cli/engine/workflow_executor.py`
- Líneas 24-42: Modificado método `execute()` para soportar `params_override`

### 2. CLI Menu
**Archivo**: `titan_cli/cli.py`
- Líneas 144-146: Agregada nueva opción al menú
- Líneas 292-357: Handler para "create_pr_with_ai"

### 3. AI PR Step (ya existente)
**Archivo**: `plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py`
- Línea 48-50: Verifica `use_ai` en `ctx.data`

### 4. Workflow YAML (ya existente)
**Archivo**: `plugins/titan-plugin-github/titan_plugin_github/workflows/create-pr.yaml`
- Línea 8: `use_ai: false` (default)

## 🎬 Flujo de Usuario

### Opción 1: Menu "Create PR with AI" (NUEVO)
```
Usuario: Ejecuta Titan CLI
  → Selecciona "Create PR with AI"
  → Sistema verifica AI configurada
  → Ejecuta workflow con use_ai=true
  → AI genera título y descripción del PR
  → Usuario confirma o modifica
  → PR creado automáticamente
```

### Opción 2: Menu "Run a Workflow" (EXISTENTE)
```
Usuario: Ejecuta Titan CLI
  → Selecciona "Run a Workflow"
  → Elige "Create Pull Request"
  → Ejecuta con use_ai=false (default)
  → Usuario introduce título y descripción manualmente
  → PR creado
```

### Opción 3: Línea de Comandos (FUTURO)
```bash
# Con AI
titan workflow run create-pr --param use_ai=true

# Sin AI (default)
titan workflow run create-pr
```

## 🔧 Arquitectura

### Flujo de Parámetros

```
Menu Option (create_pr_with_ai)
    ↓
params_override = {"use_ai": True}
    ↓
WorkflowExecutor.execute(workflow, ctx, params_override)
    ↓
ctx.data.update({"use_ai": True, ...other workflow params})
    ↓
ai_suggest_pr_description(ctx)
    ↓
use_ai = ctx.data.get("use_ai", False)  # Returns True
    ↓
AI Step Executes
```

### Compatibilidad Backward

- ✅ Workflows existentes siguen funcionando sin cambios
- ✅ `params_override` es opcional (default: None)
- ✅ Si no se pasa override, usa params del YAML
- ✅ Paso AI verifica explícitamente `use_ai` flag

## ✅ Tests

### Tests de Unit (35 tests - PASSING)
```bash
poetry run pytest tests/agents/ -v
# 35 passed in 0.21s
```

### Tests de Opt-In (4 tests - PASSING)
```bash
poetry run python test_opt_in_behavior.py
# 4 passed, 0 failed
```

### Tests de Workflow Execution (2 tests - PASSING)
```bash
poetry run python test_workflow_execution.py
# 2 passed, 0 failed
```

## 🎯 Casos de Uso

### Caso 1: Desarrollador con IA configurada
```
Desarrollador hace cambios → Abre Titan CLI →
"Create PR with AI" → AI genera descripción profesional →
Confirma y crea PR
```

**Beneficio**: Ahorra tiempo escribiendo descripciones de PR

### Caso 2: Desarrollador sin IA configurada
```
Desarrollador hace cambios → Abre Titan CLI →
"Create PR with AI" → Error: "AI no configurada" →
Usa "Run a Workflow" → Introduce descripción manualmente
```

**Beneficio**: Guía clara para configurar IA

### Caso 3: Equipo que prefiere control manual
```
Equipo hace cambios → Abre Titan CLI →
"Run a Workflow" → "Create Pull Request" →
Introduce datos manualmente (determinístico)
```

**Beneficio**: Comportamiento predecible sin IA

## 🚀 Próximos Pasos (Opcional)

### 1. Indicador Visual de IA
Mostrar en el menú si IA está configurada:
```
⚡ Workflows
  • Run a Workflow
  • Create PR with AI 🤖 (AI Ready)
```

### 2. Configuración Rápida
Si IA no configurada, ofrecer configurar desde el mismo flujo:
```
AI not configured. Would you like to configure it now? [Y/n]
```

### 3. Comando CLI
Agregar comando directo:
```bash
titan pr create --ai
```

### 4. Otros Workflows con IA
Aplicar el mismo patrón a:
- "Commit with AI-generated message"
- "Code Review with AI analysis"
- "Documentation with AI suggestions"

## 📚 Documentación

- [AI_OPT_IN_SUMMARY.md](AI_OPT_IN_SUMMARY.md) - Explicación del comportamiento opt-in
- [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) - Integración de PlatformAgent
- Este archivo - Implementación del menú con IA

## ✅ Checklist de Implementación

- [x] Modificar WorkflowExecutor para soportar params_override
- [x] Agregar opción "Create PR with AI" al menú
- [x] Implementar handler que ejecuta con use_ai=true
- [x] Verificar que AI esté configurada antes de ejecutar
- [x] Todos los tests pasando (35 agent tests + 4 opt-in tests + 2 workflow tests)
- [x] Backward compatibility mantenida
- [x] Documentación actualizada

---

**Implementado por**: Claude Code
**Fecha**: 2025-12-05
**Branch**: feat/workflow
