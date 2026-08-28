# Jira Built-in Workflows

The Jira plugin ships workflows for issue analysis and issue creation.

## `analyze-jira-issues`

Searches Jira issues, lets the user select one, and analyzes the selected issue with AI.

**Source workflow:** `plugins/titan-plugin-jira/titan_plugin_jira/workflows/analyze-jira-issues.yaml`

### Default flow

1. `jira.search_saved_query`
2. `jira.prompt_select_issue`
3. `jira.ai_analyze_issue_requirements`

### Typical usage

- triage open work before implementation
- get an AI-assisted requirements breakdown from an existing Jira issue

## `create-generic-issue`

Guides the user through issue creation, enhances the description with AI, and creates the Jira issue.

**Source workflow:** `plugins/titan-plugin-jira/titan_plugin_jira/workflows/create-generic-issue.yaml`

### Default flow

1. `jira.prompt_issue_description`
2. `jira.select_issue_type`
3. `jira.select_issue_priority`
4. `jira.ai_enhance_issue_description`
5. `jira.review_issue_description`
6. `jira.confirm_assignee_for_new_issue`
7. `before_create_issue` hook
8. `jira.create_generic_issue`

### Hooks

- `before_create_issue`: inject project-specific validation or field enrichment before issue creation

### Example extension

```yaml
extends: "plugin:jira/create-generic-issue"

hooks:
  before_create_issue:
    - id: set_component
      name: "Enrich Jira Fields"
      plugin: project
      step: prepare_jira_fields
```

## `plan-jira-issue`

Resolves a Jira issue (by number, full key, or from the board's "Ready to Dev" list), fetches
its full details and comments, and hands that context to an external AI coding CLI (chosen by
the user, e.g. Claude Code) with instructions to study the issue, break the work into steps,
and confirm the plan. The workflow then offers to assign the issue to the current user and
creates `feature/<JIRA-KEY>` from the latest `origin/develop` in an isolated worktree. The
implementation, unit tests, commit, push, and PR creation all run in that worktree, leaving
the user's current branch and working tree untouched.

**Source workflow:** `plugins/titan-plugin-jira/titan_plugin_jira/workflows/plan-jira-issue.yaml`

### Default flow

1. `jira.select_jira_issue`
2. `jira.get_issue`
3. `jira.get_comments`
4. `jira.build_jira_task_context`
5. `core.ai_code_assistant`
6. `jira.confirm_and_assign_issue`
7. `git.create_worktree` (`feature/<JIRA-KEY>` from `origin/develop`)
8. `git.activate_worktree_context`
9. `core.ai_code_assistant`
10. `create-pr-ai` nested workflow
11. `git.cleanup_worktree_context`

### Typical usage

- hand off a Jira issue to an AI coding assistant to plan before touching code
- let the user pick which installed CLI (Claude, Gemini, ...) does the planning
- claim the issue for yourself in Jira after planning, without leaving the terminal
- start every implementation from the latest remote `develop`
- isolate the predictable `feature/<JIRA-KEY>` branch from the user's current working tree
- implement the confirmed work with unit tests for main, edge, and failure cases
- reuse the project's `commit-ai` validation and GitHub `create-pr-ai` delivery workflows

### Parameters

- `base_branch`: Branch used as the implementation starting point. Defaults to `develop`.
- `branch_prefix`: Prefix for the generated `<prefix>/<JIRA-KEY>` branch. Defaults to `feature`.
- `remote`: Remote used to update and push the branch. Defaults to `origin`.
- `pr_base_branch`: Pull request target branch. Defaults to `develop`.

### Requirements and constraints

- The Jira, Git, and GitHub plugins must be enabled.
- An external AI coding CLI must be installed for the planning and implementation steps.
- The generated feature branch must not already exist locally.
- Declining the implementation step stops the workflow before a commit, push, or pull request.
- `create-pr-ai` uses the project override of `commit-ai` when one exists, so project-specific
  linting and test hooks remain in effect.
- Successful delivery removes the temporary worktree. If implementation or PR creation fails,
  the worktree is intentionally preserved so its changes can be inspected and recovered.
