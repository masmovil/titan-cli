# Titan Local Headless Runtime

## Goal

Titan native clients should execute and observe workflows without depending on a
remote HTTP backend, Docker, or terminal-only UI behavior.

The macOS app must consume a stable, UI-agnostic runtime contract. It should not
parse human logs, depend on Textual internals, or infer workflow shape by reading
implementation details that Titan already owns.

## Current Architecture

`TitanConfig` is the runtime composition root for the CLI:

- resolves the active project from `cwd`
- loads global `~/.titan/config.toml`
- loads project `.titan/config.toml`
- merges global and project configuration
- creates `SecretManager`
- initializes plugins through `PluginRegistry`
- creates `WorkflowRegistry`

`WorkflowRegistry` is the source of truth for workflow discovery:

- project workflows: `<project>/.titan/workflows`
- user workflows: `~/.titan/workflows`
- system workflows: bundled Titan workflows
- plugin workflows: `plugin.workflows_path`
- precedence: project, user, system, plugin
- supports `extends`, nested workflows, hooks, and plugin filtering

`WorkflowExecutor` is the source of truth for execution:

- plugin steps
- project steps
- user steps
- core steps
- command steps
- nested workflow steps
- shared `ctx.data`
- `requires`
- `on_error`

`TextualWorkflowExecutor` has the richest event model today, but it is coupled
to Textual messages.

`WorkflowService` is the closest reusable headless facade today. It already
supports:

- listing workflows
- starting runs
- in-memory run state
- run events
- prompt requests
- prompt responses
- SSE-style event streaming for the HTTP API

## Product Model

Native clients should model these concepts explicitly:

- `Project`: local Titan-configured folder.
- `Plugin`: configured/loaded integration, with load and init status.
- `Workflow`: executable definition discovered by Titan.
- `WorkflowStep`: resolved step metadata inside a workflow.
- `WorkflowRun`: execution instance.
- `RunEvent`: structured lifecycle or output event.
- `PromptRequest`: UI-agnostic prompt emitted by a run.
- `PromptResponse`: answer submitted by the client.
- `SecretRequirement`: missing or invalid runtime credential.

## Required Runtime Contract

The local runtime should expose a machine-readable contract that is clean by
default:

```bash
titan headless workflows list --project-path /path/to/project --json
titan headless workflows describe <workflow-name> --project-path /path/to/project --json
titan headless runs start <workflow-name> --project-path /path/to/project --params-json '{}' --ai-cli-id claude --json
titan headless runs get <run-id> --json
titan headless runs events <run-id> --json
titan headless prompts respond <run-id> <prompt-id> --value-json '{}' --json
```

The command group name should make the contract explicit. `headless` is preferred
over adding machine-only behavior to interactive commands.

## Output Rules

Headless commands must obey these rules:

- `stdout` contains only the JSON response.
- human logs never go to `stdout`.
- diagnostic logs go to a log file or `stderr`.
- non-zero exits still return a JSON error on `stderr`.
- JSON fields use stable snake_case names.
- event payloads remain JSON objects, not stringified blobs.

## Workflow List Response

```json
{
  "items": [
    {
      "name": "commit-ai",
      "description": "Create a commit with AI-generated message.",
      "source": "project",
      "title": "Commit with AI",
      "category": "git",
      "required_plugins": ["git"],
      "tags": {},
      "steps": [
        {
          "id": "git_status",
          "name": "Git Status",
          "type": "plugin",
          "plugin": "git",
          "step": "status",
          "workflow": null,
          "command": null,
          "requires": [],
          "on_error": "fail"
        }
      ]
    }
  ],
  "diagnostics": []
}
```

`steps` should come from resolved `ParsedWorkflow`, not only from lightweight
`WorkflowInfo`, because the native app needs the real workflow hierarchy.

## Run Event Model

Minimum event types:

- `workflow_run_created`
- `workflow_run_started`
- `workflow_run_completed`
- `workflow_run_failed`
- `workflow_run_resumed`
- `step_started`
- `step_finished`
- `step_failed`
- `step_skipped`
- `run_output`
- `prompt_requested`
- `prompt_answered`

Every event should include:

```json
{
  "type": "step_started",
  "run_id": "uuid",
  "timestamp": "2026-04-26T13:00:00Z",
  "payload": {
    "step_id": "search_open_issues",
    "step_name": "Search Open Issues",
    "step_index": 1,
    "plugin": "jira"
  }
}
```

## Adapter Boundary

Native clients should depend on a workflow adapter protocol:

```text
WorkflowAdapter
  listWorkflows(project)
  describeWorkflow(project, workflowName)
  startRun(project, workflowName, params)
  getRun(runID)
  getRunEvents(runID)
  respondToPrompt(runID, promptID, value)
```

Implementations:

- `HTTPWorkflowAdapter`: talks to Titan API.
- `LocalHeadlessCLIWorkflowAdapter`: launches headless CLI commands.
- future `EmbeddedRuntimeAdapter`: talks to a local helper process.

The app should not know which adapter is live.

## Non-Goals

- Do not parse terminal-oriented logs as data.
- Do not duplicate workflow discovery by reading all YAML directly in the app.
- Do not make the app import Python modules directly.
- Do not make Textual messages part of the public headless contract.
- Do not require Docker for local native execution.

## Implementation Plan

1. Add a dedicated `headless` Typer group.
2. Make `headless` bypass console logging and write logs only to file or `stderr`.
3. Add serializer functions for `WorkflowInfo`, resolved `ParsedWorkflow`, `WorkflowStepModel`, `RunSession`, `RunEvent`, and `PromptRequest`.
4. Add `WorkflowService.describe_workflow(project_path, workflow_name)`.
5. Add file-backed run storage for CLI headless mode, or explicitly document that one-shot CLI mode can only return synchronous run results.
6. Update the macOS app to use `LocalHeadlessCLIWorkflowAdapter`.
7. Keep HTTP API as a second adapter for remote/server workflows.
