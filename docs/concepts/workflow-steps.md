# Workflow Steps

Workflow steps are Python functions that Titan can execute from a workflow.

This page explains how to write them, how they receive and return data, and when to use each kind of step source.

## What a step function looks like

Every step function follows the same basic signature:

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit


def my_step(ctx: WorkflowContext) -> WorkflowResult:
    return Success("Done")
```

The function name must exactly match the `step:` value used in YAML.

```python
# .titan/steps/run_linter.py
def run_linter(ctx: WorkflowContext) -> WorkflowResult:
    ...
```

```yaml
- plugin: project
  step: run_linter
```

## Where steps can come from

| Step source | YAML form | Typical use |
|-------------|-----------|-------------|
| Plugin step | `plugin: git`, `plugin: github`, `plugin: jira` | Reuse built-in or plugin-provided capabilities |
| Project step | `plugin: project` | Repository-specific Python logic |
| User step | `plugin: user` | Personal reusable steps in `~/.titan/steps/` |
| Core step | `plugin: core` | Built-in Titan helpers |

## Reading data from the workflow context

Use `ctx.get(...)` to read values from the current workflow context.

```python
branch_name = ctx.get("branch_name")
draft = ctx.get("draft", False)
```

Those values can come from:

- workflow `params`
- step `params`
- metadata returned by earlier steps

## Returning data to later steps

There are two ways to make values available to later steps:

- `ctx.set("key", value)` while the step is running
- `metadata={...}` on `Success(...)` or `Skip(...)`

Both end up in the workflow context. In practice, project and plugin steps often use `ctx.set(...)` while building up values during the step, then return a plain `Success(...)` at the end.

```python
ctx.set("branch_name", "feat/search")
return Success("Branch created")
```

Later steps can then read that value with `ctx.get("branch_name")`.

## Result types

Step functions return one of these result types:

```python
from titan_cli.engine import Success, Skip, Error, Exit
```

### `Success`

Use when the step completed successfully.

### `Skip`

Use when the step had nothing to do, but the rest of the workflow should continue.

### `Error`

Use when the step failed.

### `Exit`

Use when the whole workflow should stop early in a controlled way.

If cleanup steps still need to run, prefer `Skip` over `Exit`.

## A minimal project step

```python
import subprocess

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error


def run_tests(ctx: WorkflowContext) -> WorkflowResult:
    result = subprocess.run(["pytest"], capture_output=True, text=True)

    if result.returncode != 0:
        return Error("Tests failed")

    return Success("Tests passed")
```

## A step that passes data forward

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error


def choose_branch(ctx: WorkflowContext) -> WorkflowResult:
    branch_name = ctx.get("branch_name")
    if not branch_name:
        return Error("Missing branch_name")

    ctx.set("selected_branch", branch_name)
    return Success("Branch selected")
```

## When to use a command step instead

Use a command step when:

- the action is a straightforward shell command
- no custom Python branching is needed
- no `ctx.textual` UI interaction is needed
- no reusable Python logic is being introduced

Use a project step when:

- you need Python conditionals or parsing
- you want to pass structured metadata to later steps
- you want to use `ctx.textual`
- the command version would be awkward or unsafe

## Using `ctx.textual`

If you want your step to look and feel like the rest of Titan, use `ctx.textual`.

That lets you:

- show step headers and status
- display formatted text, markdown, panels, and tables
- ask for user input interactively
- show loading indicators during long operations

See [Textual in Steps](textual-steps.md) for the public API.

## Using built-in clients inside steps

When Titan builds the workflow context, some steps can access ready-to-use clients directly from `ctx`.

Common examples:

- `ctx.git` for Git operations
- `ctx.github` for GitHub operations
- `ctx.jira` for Jira operations
- `ctx.ai` for AI-powered operations when AI is configured

Always check that the client you need is available before using it.

### Example: using `ctx.git`

```python
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error


def show_git_status(ctx: WorkflowContext) -> WorkflowResult:
    if not ctx.git:
        return Error("Git client is not available")

    result = ctx.git.get_status()

    match result:
        case ClientSuccess(data=status):
            ctx.set("git_status", status)
            return Success("Git status loaded")
        case ClientError(error_message=err):
            return Error(f"Failed to get git status: {err}")
```

Typical use cases:

- inspect repository state
- get the current branch
- create commits or push branches

### Example: using `ctx.github`

```python
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error


def fetch_pull_request(ctx: WorkflowContext) -> WorkflowResult:
    if not ctx.github:
        return Error("GitHub client is not available")

    pr_number = ctx.get("pr_number")
    if not pr_number:
        return Error("Missing pr_number")

    result = ctx.github.get_pull_request(int(pr_number))

    match result:
        case ClientSuccess(data=pr):
            ctx.set("pr_info", pr)
            return Success("Pull request loaded")
        case ClientError(error_message=err):
            return Error(f"Failed to fetch PR: {err}")
```

Typical use cases:

- fetch PR or issue data
- create pull requests or issues
- request reviews or submit review actions

### Example: using `ctx.jira`

```python
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error


def load_jira_issue(ctx: WorkflowContext) -> WorkflowResult:
    if not ctx.jira:
        return Error("Jira client is not available")

    issue_key = ctx.get("jira_issue_key")
    if not issue_key:
        return Error("Missing jira_issue_key")

    result = ctx.jira.get_issue(key=issue_key)

    match result:
        case ClientSuccess(data=issue):
            ctx.set("jira_issue", issue)
            return Success("Jira issue loaded")
        case ClientError(error_message=err):
            return Error(f"Failed to fetch Jira issue: {err}")
```

Typical use cases:

- load issue details
- search issues with JQL
- transition issues or assign fix versions

### Pattern to follow

When using built-in clients in steps:

1. check that the client exists on `ctx`
2. read required inputs from `ctx.get(...)`
3. call the client method
4. handle `ClientSuccess` and `ClientError`
5. return `Success`, `Skip`, or `Error` with useful metadata for later steps

If your step also needs a consistent UI, combine this pattern with [Textual in Steps](textual-steps.md).

## Built-in core steps

Titan also exposes built-in reusable steps through `plugin: core`.

These are not tied to a specific plugin like Git or GitHub. Use them when Titan already provides a generic capability directly.

### `ai_code_assistant`

Launches an external AI coding assistant CLI with context collected earlier in the workflow.

Typical use cases:

- after linting to help fix remaining lint errors
- after test failures to help diagnose or propose fixes
- after a validation step that stores machine-readable output in `ctx.data`

Example YAML:

```yaml
- id: ai-help-tests
  name: "AI Help - Tests"
  plugin: core
  step: ai_code_assistant
  params:
    context_key: "step_output"
    prompt_template: "Help me fix these failing tests:\n\n{context}"
    ask_confirmation: true
    fail_on_decline: false
```

Supported params:

- `context_key`: required key in `ctx.data` to read context from
- `prompt_template`: prompt template using `{context}` placeholder
- `ask_confirmation`: ask the user before launching the assistant
- `fail_on_decline`: return `Error` instead of `Skip` if the user declines
- `pre_launch_warning`: optional warning text shown just before the CLI starts

Which CLI runs is **not** a step param. It is the default CLI chosen once in
**AI Configuration → CLI**, so every workflow uses the same one and nothing is asked
mid-run. Users can also route this task to `Off` under **AI Configuration → AI per task**,
in which case the step skips.

Behavior:

- returns `Skip` if there is no context under `context_key`
- returns `Skip` if no supported assistant CLI is installed at all
- returns `Skip` if the user turned this task off
- returns `Error` if required params are missing or invalid
- returns `Error` if no default CLI is configured, or the configured one is not installed
- returns `Error` if the launched CLI exits with a non-zero code
- returns `Success` when the assistant exits successfully

Notes:

- The step clears the consumed `context_key` from `ctx.data` after reading it, so later steps do not accidentally reuse stale context.
- This step uses Titan's Textual UI and temporarily suspends the TUI while the external CLI runs.

## Recommended structure for public plugin steps

If you are exposing a public step from a plugin through `get_steps()`, treat it as part of the plugin's public API.

Use a canonical docstring structure:

```python
def my_public_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    One-line summary.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        pr_number (int): Pull request number to inspect.

    Outputs (saved to ctx.data):
        pr_info: The fetched pull request object.

    Returns:
        Success: If the step completes successfully.
        Error: If required context is missing or execution fails.
    """
```

This is especially important for public plugin docs and generated step inventories.

## Common mistakes

- function name does not match `step:` in YAML
- using `Exit` when `Skip` is the right result
- forgetting to return metadata that later steps need
- using a Python step for logic that could just be a simple command step
- writing custom UI output instead of using `ctx.textual`

## What to read next

- [Workflows](workflows.md)
- [Textual in Steps](textual-steps.md)
- [Your First Workflow](../getting-started/your-first-workflow.md)
