# Git Step Reference

This page is generated from the public step inventory and shows the documented workflow contract for each public step.

## Status and Inspection

### `get_status`

Retrieves the current git status and saves it to the context.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: get_status
```

**Used by built-in workflows:** `commit-ai`

**Available to later steps:** `git_status`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `git_status` | GitStatus | The full git status object, which includes the `is_clean` flag. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `git_status` | If there are changes to commit (workflow continues) |
| `Exit` | - | If working directory is clean (stops commit workflow; parent continues) |
| `Error` | - | If the GitClient is not available or the git command fails. |

### `get_current_branch`

Retrieves the current git branch name and saves it to the context.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: get_current_branch
```

**Available to later steps:** `pr_head_branch`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `pr_head_branch` | str | The name of the current branch, to be used as the head branch for a PR. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `pr_head_branch` | If the current branch was retrieved successfully. |
| `Error` | - | If the GitClient is not available or the git command fails. |

### `get_base_branch`

Retrieves the configured main/base branch name and saves it to the context.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: get_base_branch
```

**Available to later steps:** `pr_base_branch`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `pr_base_branch` | str | The name of the base branch, to be used as the base branch for a PR. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `pr_base_branch` | If the base branch was retrieved successfully. |
| `Error` | - | If the GitClient is not available or the git command fails. |

## Commits

### `create_commit`

Creates a git commit.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: create_commit
```

**Used by built-in workflows:** `commit-ai`

**Available to later steps:** `commit_hash`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `git_status` | GitStatus | The git status object, used to check if the working directory is clean. |
| `commit_message` | str | The message for the commit. |
| `all_files` | bool, optional | Whether to commit all modified and new files. Defaults to True. |
| `no_verify` | bool, optional | Skip pre-commit and commit-msg hooks. Defaults to False. |
| `commit_hash` | str, optional | If present, indicates a commit was already created. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `commit_hash` | str | The hash of the created commit. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `commit_hash` | If the commit was created successfully. |
| `Error` | - | If the GitClient is not available, or the commit operation fails. |
| `Skip` | `commit_hash` | If there are no changes to commit or a commit was already created. |

### `push`

Pushes changes to a remote repository.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: push
```

**Used by built-in workflows:** `commit-ai`

**Available to later steps:** `pr_head_branch`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `pr_head_branch` | str | The name of the branch that was pushed. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `pr_head_branch` | If the push was successful. |
| `Error` | - | If the push operation fails. |

### `ai_generate_commit_message`

Generate a commit message using AI based on the current changes.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: ai_generate_commit_message
```

**Used by built-in workflows:** `commit-ai`

**Available to later steps:** `commit_message`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |
| `ctx.ai` | - | An initialized AIClient. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `git_status` | - | Current git status with changes. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `commit_message` | str | AI-generated commit message. |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `commit_message` | If the commit message was generated successfully. |
| `Error` | - | If the operation fails. |
| `Skip` | `commit_message` | If no changes, AI not configured, or user declined. |

## Branching

### `save_current_branch`

Save current branch and stash uncommitted changes.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: save_current_branch
```

**Available to later steps:** `original_branch`, `has_stashed_changes`

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `original_branch` | str | Name of the branch the user was on |
| `has_stashed_changes` | bool | Whether changes were stashed |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `original_branch`, `has_stashed_changes` | Branch saved and changes stashed if needed |
| `Error` | - | Git operation failed |

### `restore_original_branch`

Restore original branch and pop stashed changes.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: restore_original_branch
```

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `original_branch` | str | Name of the branch to restore |
| `has_stashed_changes` | bool | Whether to pop stashed changes |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Branch restored and changes popped if needed |
| `Error` | - | Git operation failed |

### `checkout`

Checkout a Git branch.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: checkout
```

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `branch` | str | Branch name to checkout |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Branch checked out successfully |
| `Error` | - | Git operation failed |

### `pull`

Pull from Git remote.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: pull
```

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `remote` | str, optional | Remote name (defaults to "origin") |
| `branch` | str, optional | Branch name (defaults to current branch) |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Pull completed successfully |
| `Error` | - | Git operation failed |

### `create_branch`

Create a new Git branch.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: create_branch
```

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `new_branch` | str | Name of the branch to create |
| `start_point` | str, optional | Starting point for the branch (defaults to HEAD) |
| `delete_if_exists` | bool, optional | Delete the branch if it already exists (default: False) |
| `checkout` | bool, optional | Checkout the new branch after creation (default: True) |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Branch created successfully |
| `Error` | - | Git operation failed |

## Merging

### `resolve_merge_target`

Resolve which branch gets merged and verify the repo is ready for it.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: resolve_merge_target
```

**Used by built-in workflows:** `merge-branch`

**Available to later steps:** `source_branch`, `target_branch`, `remote`, `merge_ref`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |
| `ctx.textual` | - | The Textual UI context. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `source_branch` | str, optional | Branch to merge (defaults to the configured base branch) |
| `remote` | str, optional | Remote name (default: "origin") |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `source_branch` | str | Resolved branch to merge |
| `target_branch` | str | Branch receiving the merge |
| `remote` | str | Remote name |
| `merge_ref` | str | Ref that will be merged, e.g. "origin/develop" |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `source_branch`, `target_branch`, `remote`, `merge_ref` | Target resolved |
| `Exit` | - | Working tree is dirty, nothing was touched |
| `Error` | - | Git client unavailable or the branch cannot be resolved |

### `fetch_merge_source`

Fetch the source branch from the remote without moving HEAD.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: fetch_merge_source
```

**Used by built-in workflows:** `merge-branch`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |
| `ctx.textual` | - | The Textual UI context. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `source_branch` | str | Branch to fetch |
| `remote` | str | Remote name |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Remote-tracking ref updated |
| `Error` | - | Fetch failed or required inputs are missing |

### `merge_source_branch`

Merge the fetched ref into the current branch.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: merge_source_branch
```

**Used by built-in workflows:** `merge-branch`

**Available to later steps:** `merge_status`, `merge_conflicts`, `merge_conflict_context`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |
| `ctx.textual` | - | The Textual UI context. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `merge_ref` | str | Ref to merge, e.g. "origin/develop" |
| `target_branch` | str | Branch receiving the merge |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `merge_status` | str | One of up_to_date / fast_forward / merged / conflicted |
| `merge_conflicts` | list | Paths with unresolved conflicts (empty when clean) |
| `merge_conflict_context` | str | Prompt for the AI CLI, only set on conflicts |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `merge_status`, `merge_conflicts`, `merge_conflict_context` | Merge finished, cleanly or with conflicts to resolve |
| `Error` | - | Git refused to start the merge |

### `complete_merge`

Finish a conflicted merge after the user resolved the conflicts.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: complete_merge
```

**Used by built-in workflows:** `merge-branch`

**Available to later steps:** `merge_commit_sha`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.git` | - | An initialized GitClient. |
| `ctx.textual` | - | The Textual UI context. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `merge_status` | str | Status published by merge_source_branch |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `merge_commit_sha` | str | SHA of the merge commit |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `merge_commit_sha` | Merge committed |
| `Skip` | `merge_commit_sha` | Merge was already complete, nothing to do |
| `Exit` | - | User aborted the merge |
| `Error` | - | Staging or committing failed |

## Diff Summaries

### `show_uncommitted_diff_summary`

Show uncommitted changes and let the user select which files to include

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: show_uncommitted_diff_summary
```

**Used by built-in workflows:** `commit-ai`

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Files selected and saved to context |
| `Exit` | - | No files selected by the user |
| `Skip` | - | Could not retrieve diff stat |

### `show_branch_diff_summary`

Show summary of branch changes (git diff base...head --stat).

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: show_branch_diff_summary
```

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `pr_head_branch` | str | Head branch name |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | Always (even if no changes, for workflow continuity) |

## Worktrees

### `create_worktree`

Create a temporary git worktree in detached HEAD mode from a remote base branch.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: create_worktree
```

**Available to later steps:** `worktree_path`, `base_branch`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `base_branch` | str, optional | Base branch to create the worktree from. Defaults to the git plugin's configured main branch. |
| `path` | str, optional | Custom path for the worktree. Defaults to a temporary directory. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `worktree_path` | str | Path to the created worktree. |
| `base_branch` | str | Base branch name (e.g., "develop", "main" or "rc/26.18.2"). |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `worktree_path`, `base_branch` | If the worktree is created successfully. |
| `Error` | - | If the Git client is unavailable, no base branch can be resolved, or worktree creation fails. |

### `remove_worktree`

Remove a git worktree.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: remove_worktree
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the worktree is removed successfully or is already gone. |
| `Error` | - | If cleanup fails. |

### `worktree_commit`

Create a commit in a worktree.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: worktree_commit
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the commit is created in the worktree. |
| `Error` | - | If required context is missing or the git command fails. |

### `worktree_push`

Push from a worktree.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: git
  step: worktree_push
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the branch is pushed from the worktree. |
| `Error` | - | If required context is missing or the git command fails. |
