# Workflow Step Rules

Rules for authoring workflow steps in Titan CLI.

## Step Data Outputs

Do not write step outputs directly into `ctx.data` when returning from a step.

Prefer returning outputs through `Success(metadata={...})`, `Skip(metadata={...})`, or `Exit(metadata={...})`. The workflow executor automatically merges result metadata into `ctx.data` for subsequent steps.

Use local variables inside the current step. Use `ctx.data` or `ctx.set()` only when data must be available through the context before the step returns, or when an existing API explicitly requires context mutation.

Bad:

```python
ctx.data["existing_comments_index"] = index

return Success(
    "Comments index built",
    metadata={"existing_comments_index": index},
)
```

Good:

```python
return Success(
    "Comments index built",
    metadata={"existing_comments_index": index},
)
```

## Steps That Use AI

Any step that makes an AI call must declare it with `declare_ai_usage` and route the call
through `ctx.ai_router`. The declaration is the step's contract with the configuration UI
and the router — this applies to official plugins, project steps, and community plugins alike.

```python
from titan_cli.ai.router import AIProviderType, AITask, declare_ai_usage

@declare_ai_usage(
    task=AITask.COMMIT_MESSAGE,        # or your own stable string for community tasks
    executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
    preferred=[AIProviderType.REMOTE], # optional; defaults to executes order
    enforces=True,
)
def my_step(ctx: WorkflowContext) -> WorkflowResult:
    ...
```

What each field means — and what it commits you to:

- **`task`** is the key users configure a provider for ("for commit messages, use X").
  Reuse an `AITask` member when one fits; several steps sharing a task share one setting.
- **`executes`** is the set of provider types your code can actually run. The preferences
  UI offers users nothing outside it, and the resolver refuses a persisted preference that
  falls outside it. Never declare a type your code can't drive; never drive one you didn't
  declare.
  - One prompt in / one text out via `ctx.ai_router.generate_text()` → can honestly declare
    `REMOTE` and `CLI_HEADLESS`.
  - Handing a generator to an agent (multi-call) via `ctx.ai_router.resolve_generator()` →
    can honestly declare `REMOTE` and `CLI_HEADLESS`. Prefer `REMOTE`: a CLI costs one
    subprocess per agent call. See [ai-agents.md](ai-agents.md).
  - Launching an interactive session that edits files / runs commands → `CLI_INTERACTIVE`
    only, and use `ctx.ai_router.resolve()` instead of `generate_text()`.
- **`preferred`** is the default try-order when the user configured nothing. It must be a
  subset of `executes` (the decorator raises `ValueError` otherwise). Omit it when it
  matches `executes`.
- **`enforces`** says your code actually consults `ctx.ai_router` at runtime. Only set it
  `True` when that is true — a declaring-but-not-enforcing step shows up in the UI with a
  "may not honor this setting" warning instead of lying.

Runtime rules:

- Never ask the user to pick a provider mid-workflow; routing is configured beforehand in
  the AI Configuration screen. An inline pick, where one still exists, applies to that run
  only.
- Never persist a preference from a step (`upsert_task_ai_preference` is the config
  screen's job).
- Pattern-match the result and handle `AIExecutionError(error_code="AI_DISABLED")` as a
  `Skip` — the user turned the task off; that is not an error.
- Model/effort/timeout are call-site parameters (`generate_text(model=..., timeout=...)`),
  never something a step reads from preferences.
- Pass `announce=ctx.textual.ai_chip` so the run shows which AI served the task. A user
  watching a workflow should be able to notice the wrong one without reading the log —
  that is what prompts them to change it. Skip it only where your own output already
  names the provider.

## Secrets In Steps

- Use `ctx.secret_broker` for anything credential-shaped: `exists`/`store`/
  `prompt_and_store`/`delete`/`create_client` and the use-primitives. There is
  no way to read a value back — that is the design, not a missing feature.
- Never place a raw secret (or material derived from one, like a decrypted
  key) in `ctx.data` or in `Success`/`Skip`/`Exit` metadata. The result types
  scan their metadata at construction and raise `SecretLeakError`. Wrap
  derived material in `SensitiveValue` and call `.reveal()` only at client
  construction.
- Full guide: [Secrets & Security](security.md).
