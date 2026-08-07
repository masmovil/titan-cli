# Git Built-in Workflows

The Git plugin ships two workflows: one for commit creation and push automation, and one for merging a branch into the current one.

## `commit-ai`

Creates a commit from the current working tree using an AI-generated commit message, then pushes it.

**Source workflow:** `plugins/titan-plugin-git/titan_plugin_git/workflows/commit-ai.yaml`

### Default flow

1. `git.get_status`
2. `before_commit` hook
3. `git.show_uncommitted_diff_summary`
4. `git.ai_generate_commit_message`
5. `git.create_commit`
6. `git.push`

### Hooks

- `before_commit`: inject validation or preparation steps before the commit is created

### Typical extension points

- run lints before committing
- run tests before committing
- collect extra project context before AI commit message generation

### Example extension

```yaml
extends: "plugin:git/commit-ai"

hooks:
  before_commit:
    - id: lint
      name: "Run Ruff"
      command: "poetry run ruff check ."
      on_error: fail
```

### Related public steps

- `get_status`
- `show_uncommitted_diff_summary`
- `ai_generate_commit_message`
- `create_commit`
- `push`

## `merge-branch`

Merges another branch into the branch you are on. When the merge conflicts, it hands the terminal to the configured interactive AI CLI so you can resolve the conflicts, then finishes the merge when you exit.

HEAD never moves: the source branch is fetched and merged through its remote-tracking ref, so a failure at any point leaves you on the branch you started on.

**Source workflow:** `plugins/titan-plugin-git/titan_plugin_git/workflows/merge-branch.yaml`

### Parameters

| Param | Default | Meaning |
|-------|---------|---------|
| `source_branch` | `""` | Branch to merge. Empty means the base branch configured for the project (`plugins.git.main_branch`). |
| `remote` | `"origin"` | Remote the source branch is fetched from. |

### Default flow

1. `before_merge` hook
2. `git.resolve_merge_target`
3. `git.fetch_merge_source`
4. `git.merge_source_branch`
5. `core.ai_code_assistant` (skips itself when there are no conflicts)
6. `git.complete_merge`
7. `after_merge` hook

### Behavior

- **Working tree must be clean.** The workflow exits before touching anything if there are uncommitted changes. A merge on a dirty tree cannot be rolled back safely once it conflicts.
- **No conflicts:** git commits the merge itself with the message it suggests. Steps 5 and 6 skip.
- **Conflicts:** the conflicted files are listed, the AI CLI is launched with a prompt describing them, and on exit `complete_merge` runs `git add --all` plus a commit with git's prepared merge message.
- **Conflicts still unresolved on exit:** you are asked whether to abort the merge (restoring the previous state) or commit as-is.

### Hooks

- `before_merge`: override `source_branch` or run pre-merge validation
- `after_merge`: run anything that depends on the merge result, for example tests or a push

### Example: always merge `develop`

```yaml
name: "Merge develop"

extends: "plugin:git/merge-branch"

params:
  source_branch: "develop"
```

### Example: push after a successful merge

```yaml
extends: "plugin:git/merge-branch"

hooks:
  after_merge:
    - id: push
      name: "Push merge"
      plugin: git
      step: push
```

### Related public steps

- `resolve_merge_target`
- `fetch_merge_source`
- `merge_source_branch`
- `complete_merge`
