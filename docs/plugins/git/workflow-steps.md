# Git Workflow Steps

The Git plugin exposes reusable public workflow steps through `GitPlugin.get_steps()`. These steps are grouped here by workflow intent so authors can discover related building blocks more easily.

For full contract details for every public step, including documented inputs, outputs, and return behavior, see the [detailed step reference](../generated/git-step-reference.md).

## Functional groups

- [Status and Inspection](#status-and-inspection)
- [Commits](#commits)
- [Branching](#branching)
- [Merging](#merging)
- [Diff Summaries](#diff-summaries)
- [Worktrees](#worktrees)

## Summary

| Step | Group | Used by built-in workflows |
|------|-------|----------------------------|
| `get_status` | Status and Inspection | `commit-ai` |
| `get_current_branch` | Status and Inspection | `create-pr-ai` |
| `get_base_branch` | Status and Inspection | - |
| `create_commit` | Commits | `commit-ai` |
| `push` | Commits | `commit-ai`, `create-pr-ai` |
| `ai_generate_commit_message` | Commits | `commit-ai` |
| `save_current_branch` | Branching | - |
| `restore_original_branch` | Branching | - |
| `checkout` | Branching | - |
| `pull` | Branching | - |
| `create_branch` | Branching | - |
| `resolve_merge_target` | Merging | `merge-branch` |
| `fetch_merge_source` | Merging | `merge-branch` |
| `merge_source_branch` | Merging | `merge-branch` |
| `complete_merge` | Merging | `merge-branch` |
| `show_uncommitted_diff_summary` | Diff Summaries | `commit-ai` |
| `show_branch_diff_summary` | Diff Summaries | `create-pr-ai` |
| `create_worktree` | Worktrees | - |
| `remove_worktree` | Worktrees | - |
| `worktree_commit` | Worktrees | - |
| `worktree_push` | Worktrees | - |

## Status and Inspection

Use these steps to inspect repository state and expose branch metadata to later steps.

- `get_status`: retrieve repository status and expose `git_status` to the workflow context
- `get_current_branch`: resolve the currently checked out branch name
- `get_base_branch`: resolve the base branch used by Git workflows

## Commits

Use these steps to prepare commit content and publish branch changes.

- `create_commit`: create a commit from workflow commit message data
- `push`: push the current branch to the configured remote
- `ai_generate_commit_message`: generate a commit message from local changes using AI

## Branching

Use these steps to switch, create, and restore branches during a workflow.

- `save_current_branch`: save the current branch in workflow context
- `restore_original_branch`: restore the saved branch later in the workflow
- `checkout`: switch to a branch from workflow context or params
- `pull`: update the current branch from the configured remote
- `create_branch`: create a new branch from workflow-provided branch data

## Merging

Use these steps to integrate another branch into the current one. HEAD never moves: the source branch is fetched and merged through its remote-tracking ref.

- `resolve_merge_target`: resolve the branch to merge and verify the working tree is clean
- `fetch_merge_source`: fetch the source branch from the remote
- `merge_source_branch`: run the merge and report conflicts as workflow data
- `complete_merge`: stage resolved conflicts and commit with git's suggested message

## Diff Summaries

Use these steps when a workflow needs human-readable or AI-friendly summaries of Git changes.

- `show_uncommitted_diff_summary`: summarize local uncommitted changes
- `show_branch_diff_summary`: summarize branch-level changes relative to the base branch

## Worktrees

Use these steps to isolate workflow work in dedicated worktrees.

- `create_worktree`: create a worktree for isolated work
- `remove_worktree`: remove a worktree when finished
- `worktree_commit`: commit changes inside a specific worktree
- `worktree_push`: push a branch from a specific worktree

<!-- BEGIN GENERATED STEP CONTRACTS -->
## Detailed Step Contracts

The summaries above show what each git step is for. The sections below show the documented contract for each public step: what it expects from `ctx.data`, what it saves back, and what result types it may return.

Expand a step to see its workflow usage, required context, inputs, outputs, and result behavior.

How to read these contracts:

- `Inputs (from ctx.data)` = values the step expects before it runs.
- `Outputs (saved to ctx.data)` = metadata keys saved for later steps when the step returns `Success` or `Skip`.
- `Returns` = the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate payload.

### Status and Inspection

??? info "`get_status`"
    Retrieves the current git status and saves it to the context.

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

    **Inputs (from ctx.data)**

    None documented.

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


??? info "`get_current_branch`"
    Retrieves the current git branch name and saves it to the context.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_head_branch` | str | The name of the current branch, to be used as the head branch for a PR. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_head_branch` | If the current branch was retrieved successfully. |
    | `Error` | - | If the GitClient is not available or the git command fails. |


??? info "`get_base_branch`"
    Retrieves the configured main/base branch name and saves it to the context.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_base_branch` | str | The name of the base branch, to be used as the base branch for a PR. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_base_branch` | If the base branch was retrieved successfully. |
    | `Error` | - | If the GitClient is not available or the git command fails. |


### Commits

??? info "`create_commit`"
    Creates a git commit.

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


??? info "`push`"
    Pushes changes to a remote repository.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_head_branch` | str | The name of the branch that was pushed. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_head_branch` | If the push was successful. |
    | `Error` | - | If the push operation fails. |


??? info "`ai_generate_commit_message`"
    Generate a commit message using AI based on the current changes.

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


### Branching

??? info "`save_current_branch`"
    Save current branch and stash uncommitted changes.

    **Workflow usage**

    ```yaml
    - plugin: git
      step: save_current_branch
    ```

    **Available to later steps:** `original_branch`, `has_stashed_changes`

    **Inputs (from ctx.data)**

    None documented.

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


??? info "`restore_original_branch`"
    Restore original branch and pop stashed changes.

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

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Branch restored and changes popped if needed |
    | `Error` | - | Git operation failed |


??? info "`checkout`"
    Checkout a Git branch.

    **Workflow usage**

    ```yaml
    - plugin: git
      step: checkout
    ```

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `branch` | str | Branch name to checkout |

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Branch checked out successfully |
    | `Error` | - | Git operation failed |


??? info "`pull`"
    Pull from Git remote.

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

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Pull completed successfully |
    | `Error` | - | Git operation failed |


??? info "`create_branch`"
    Create a new Git branch.

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

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Branch created successfully |
    | `Error` | - | Git operation failed |


### Merging

??? info "`resolve_merge_target`"
    Resolve which branch gets merged and verify the repo is ready for it.

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


??? info "`fetch_merge_source`"
    Fetch the source branch from the remote without moving HEAD.

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

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Remote-tracking ref updated |
    | `Error` | - | Fetch failed or required inputs are missing |


??? info "`merge_source_branch`"
    Merge the fetched ref into the current branch.

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


??? info "`complete_merge`"
    Finish a conflicted merge after the user resolved the conflicts.

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


### Diff Summaries

??? info "`show_uncommitted_diff_summary`"
    Show uncommitted changes and let the user select which files to include

    **Workflow usage**

    ```yaml
    - plugin: git
      step: show_uncommitted_diff_summary
    ```

    **Used by built-in workflows:** `commit-ai`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Files selected and saved to context |
    | `Exit` | - | No files selected by the user |
    | `Skip` | - | Could not retrieve diff stat |


??? info "`show_branch_diff_summary`"
    Show summary of branch changes (git diff base...head --stat).

    **Workflow usage**

    ```yaml
    - plugin: git
      step: show_branch_diff_summary
    ```

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_head_branch` | str | Head branch name |

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Always (even if no changes, for workflow continuity) |


### Worktrees

??? info "`create_worktree`"
    Create a temporary git worktree in detached HEAD mode from a remote base branch.

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


??? info "`remove_worktree`"
    Remove a git worktree.

    **Workflow usage**

    ```yaml
    - plugin: git
      step: remove_worktree
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the worktree is removed successfully or is already gone. |
    | `Error` | - | If cleanup fails. |


??? info "`worktree_commit`"
    Create a commit in a worktree.

    **Workflow usage**

    ```yaml
    - plugin: git
      step: worktree_commit
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the commit is created in the worktree. |
    | `Error` | - | If required context is missing or the git command fails. |


??? info "`worktree_push`"
    Push from a worktree.

    **Workflow usage**

    ```yaml
    - plugin: git
      step: worktree_push
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the branch is pushed from the worktree. |
    | `Error` | - | If required context is missing or the git command fails. |
<!-- END GENERATED STEP CONTRACTS -->

## Docstring-based reference

The semiautomated step inventory reads public step docstrings from code and validates that each exposed step documents:

- `Requires`
- `Inputs (from ctx.data)` when applicable
- `Outputs (saved to ctx.data)` when applicable
- `Returns`

The generated machine-readable inventory lives under `docs/plugins/_generated/`.

For this project, the inventory is maintained through:

- `.titan/workflows/sync-plugin-docs.yaml`
- `.titan/workflows/validate-plugin-docs.yaml`
- `.titan/steps/sync_plugin_docs.py`
- `.titan/steps/validate_plugin_docs.py`
