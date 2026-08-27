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
and confirm the plan with the user before implementing anything. Once the user exits that CLI
session, the workflow offers to assign the issue to the current user in Jira.

**Source workflow:** `plugins/titan-plugin-jira/titan_plugin_jira/workflows/plan-jira-issue.yaml`

### Default flow

1. `jira.select_jira_issue`
2. `jira.get_issue`
3. `jira.get_comments`
4. `jira.build_jira_task_context`
5. `core.ai_code_assistant`
6. `jira.confirm_and_assign_issue`

### Typical usage

- hand off a Jira issue to an AI coding assistant to plan the implementation before touching any code
- let the user pick which installed CLI (Claude, Gemini, ...) does the planning
- claim the issue for yourself in Jira right after planning/starting the work, without leaving the terminal
