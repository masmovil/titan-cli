# Git Plugin

The Git plugin provides Titan's core Git workflow surface. It exposes:

- a high-level `GitClient` for direct use from Titan code
- reusable workflow `steps` such as `get_status`, `create_commit`, and `push`
- the built-in `commit-ai` and `merge-branch` workflows

## Requirements

To use the Git plugin in a project:

- Enable the `git` plugin in `.titan/config.toml`
- Install the `git` CLI and make sure it is available in `PATH`
- Run Titan inside a Git repository

Example project configuration:

```toml
[plugins.git]
enabled = true

[plugins.git.config]
main_branch = "main"
default_remote = "origin"
```

## Public surfaces

- [Client API](./client-api.md): direct Python methods exposed by `GitClient`
- [Workflow Steps](./workflow-steps.md): public reusable workflow steps grouped by functionality
- [Built-in Workflows](./built-in-workflows.md): workflows shipped by the plugin

## Accessing the client

In Titan code, the public entry point is the Git plugin client:

```python
git_plugin = config.registry.get_plugin("git")
client = git_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

## Public workflow steps

The Git plugin exposes these reusable public steps through `get_steps()`:

- `get_status`
- `create_commit`
- `push`
- `get_current_branch`
- `get_base_branch`
- `ai_generate_commit_message`
- `show_uncommitted_diff_summary`
- `show_branch_diff_summary`
- `save_current_branch`
- `restore_original_branch`
- `checkout`
- `pull`
- `create_branch`
- `resolve_merge_target`
- `fetch_merge_source`
- `merge_source_branch`
- `complete_merge`
- `create_worktree`
- `remove_worktree`
- `worktree_commit`
- `worktree_push`

These steps are intended for workflow authors. Their inputs, outputs, and return behavior are documented in [Workflow Steps](./workflow-steps.md).
