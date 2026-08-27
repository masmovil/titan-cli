# Jira Step Reference

This page is generated from the public step inventory and shows the documented workflow contract for each public step.

## Search and Selection

### `search_saved_query`

Search JIRA issues using a saved query.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: search_saved_query
```

**Used by built-in workflows:** `analyze-jira-issues`

**Available to later steps:** `jira_issues`, `jira_issue_count`, `used_query_name`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `query_name` | str | Name of saved query (e.g., "my_bugs", "team_bugs") |
| `project` | str, optional | Project key for parameterized queries (e.g., "ECAPP") |
| `max_results` | int, optional | Maximum number of results (default: 50) |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issues` | list | List of JiraTicket objects |
| `jira_issue_count` | int | Number of issues found |
| `used_query_name` | str | Name of the query that was used |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_issues`, `jira_issue_count`, `used_query_name` | Issues found |
| `Error` | - | Query not found or search failed |
| `Personal` | - | my_open_issues, my_bugs, my_in_review, my_in_progress |
| `Team` | - | current_sprint, team_open, team_bugs, team_in_review |
| `Priority` | - | critical_issues, high_priority, blocked_issues |
| `Time` | - | updated_today, created_this_week, recent_bugs |
| `Status` | - | todo_issues, in_progress_all, done_recently |

### `search_jql`

Search JIRA issues using a custom JQL query.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: search_jql
```

**Available to later steps:** `jira_issues`, `jira_issue_count`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jql` | str | JQL query string (supports variable substitution with ${var_name}) |
| `max_results` | int, optional | Maximum number of results (default: 100) |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issues` | list | List of JiraTicket objects |
| `jira_issue_count` | int | Number of issues found |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_issues`, `jira_issue_count` | Issues found |
| `Error` | - | Search failed or JQL not provided |
| `You can use ${variable_name} in the JQL and it will be replaced with values from ctx.data.` | - | - |
| `Example` | - | "project = ${project_key} AND fixVersion = ${fix_version}" |

### `prompt_select_issue`

Prompt user to select a JIRA issue from search results.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: prompt_select_issue
```

**Used by built-in workflows:** `analyze-jira-issues`

**Available to later steps:** `jira_issue_key`, `selected_issue`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issues` | List[JiraTicket] | List of issues from search |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue_key` | str | Selected issue key |
| `selected_issue` | JiraTicket | Selected issue object |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_issue_key`, `selected_issue` | If the user selects a valid issue. |
| `Error` | - | If there are no issues, the selection is invalid, or the prompt is cancelled. |

### `select_jira_issue`

Resolve a JIRA issue key from user input: a plain number, a full key, or a board search.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: select_jira_issue
```

**Used by built-in workflows:** `plan-jira-issue`

**Available to later steps:** `jira_issue_key`, `selected_issue`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.jira` | - | An initialized JiraClient. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue_key` | str | The resolved JIRA issue key |
| `selected_issue` | UIJiraIssue, optional | Set only when resolved via the Ready to Dev list |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_issue_key`, `selected_issue` | An issue key was resolved |
| `Error` | - | JIRA client not available, invalid input, search failed, or no selection made |

## Issue Retrieval and Analysis

### `get_issue`

Get JIRA issue details by key.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: get_issue
```

**Used by built-in workflows:** `plan-jira-issue`

**Available to later steps:** `jira_issue`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue_key` | str | JIRA issue key (e.g., "PROJ-123") |
| `expand` | list[str], optional | Additional fields to expand |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue` | UIJiraIssue | Issue details |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_issue` | Issue retrieved |
| `Error` | - | Failed to get issue |

### `get_comments`

Get all comments for a JIRA issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: get_comments
```

**Used by built-in workflows:** `plan-jira-issue`

**Available to later steps:** `jira_comments`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| `ctx.jira` | - | An initialized JiraClient. |

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue_key` | str | JIRA issue key (e.g., "PROJ-123") |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_comments` | list[UIJiraComment] | Comments for the issue, oldest first |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_comments` | Comments retrieved (empty list if the issue has none) |
| `Error` | - | JIRA client not available, issue key missing, or the request failed |

### `ai_analyze_issue_requirements`

Analyze JIRA issue requirements using AI.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: ai_analyze_issue_requirements
```

**Used by built-in workflows:** `analyze-jira-issues`

**Available to later steps:** `ai_analysis`, `analysis_sections`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue` | JiraTicket | JIRA issue object to analyze |
| `selected_issue` | JiraTicket, optional | Alternative source |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `ai_analysis` | str | AI-generated analysis |
| `analysis_sections` | dict | Structured analysis breakdown |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `ai_analysis`, `analysis_sections` | If the issue analysis completes successfully. |
| `Skip` | `ai_analysis`, `analysis_sections` | If AI is not configured or not available. |
| `Error` | - | If no issue is available to analyze. |

## AI Planning Handoff

### `build_jira_task_context`

Build the full AI prompt for planning work on a JIRA issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: build_jira_task_context
```

**Used by built-in workflows:** `plan-jira-issue`

**Available to later steps:** `jira_task_context`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue` | UIJiraIssue | Issue details, from get_issue |
| `jira_comments` | list[UIJiraComment], optional | Issue comments, from get_comments |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_task_context` | str | Full prompt text (instructions + issue + comments) |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `jira_task_context` | Prompt built |
| `Error` | - | jira_issue is missing |

### `confirm_and_assign_issue`

Ask the user if they want to assign the current JIRA issue to themselves, and do it.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: confirm_and_assign_issue
```

**Used by built-in workflows:** `plan-jira-issue`

**Available to later steps:** `issue_assigned_to_me`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `jira_issue_key` | str | JIRA issue key to assign |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `issue_assigned_to_me` | bool | Whether the issue was assigned to the current user |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `issue_assigned_to_me` | Issue assigned, or user declined to assign it |
| `Error` | - | JIRA client not available, issue key missing, or the assignment call failed |

## Transitions and Fix Versions

### `get_transitions`

Fetch available transitions for a Jira issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: get_transitions
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If transitions are fetched successfully. |
| `Error` | - | If required context is missing or the Jira call fails. |

### `transition_issue`

Transition a Jira issue to a target status.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: transition_issue
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the issue transitions successfully. |
| `Error` | - | If required context is missing or the Jira call fails. |

### `verify_issue_state`

Verify that a Jira issue is currently in the expected status.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: verify_issue_state
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the issue is in the expected status. |
| `Error` | - | If required context is missing, verification fails, or the Jira call fails. |

### `list_versions`

List unreleased versions for a JIRA project.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: list_versions
```

**Available to later steps:** `versions`, `versions_full`

**Inputs (from ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `project_key` | str, optional | Project key. If not provided, uses default_project from JIRA plugin config. |

**Outputs (saved to ctx.data)**

| Name | Type | Description |
|------|------|-------------|
| `versions` | list | List of unreleased version names |
| `versions_full` | list | List of full unreleased version objects |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | `versions`, `versions_full` | Unreleased versions listed |
| `Error` | - | Failed to fetch versions or project_key not configured |

### `create_version`

Create a Jira version.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: create_version
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the version is created successfully. |
| `Error` | - | If required context is missing or the Jira call fails. |

### `ensure_version_exists`

Ensure a Jira version exists, creating it if missing.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: ensure_version_exists
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the version already exists or is created successfully. |
| `Error` | - | If required context is missing or the Jira call fails. |

### `assign_fix_version`

Assign a fixVersion to a Jira issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: assign_fix_version
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the fix version is assigned successfully. |
| `Error` | - | If required context is missing or the Jira call fails. |

### `verify_issue_has_fix_version`

Verify a Jira issue has the expected fixVersion.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: verify_issue_has_fix_version
```

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `Success` | - | If the issue has the expected fix version. |
| `Error` | - | If required context is missing, verification fails, or the Jira call fails. |

## Issue Creation

### `prompt_issue_description`

Prompt user for brief description of the issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: prompt_issue_description
```

**Used by built-in workflows:** `create-generic-issue`

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `select_issue_type`

Select issue type for the new issue.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: select_issue_type
```

**Used by built-in workflows:** `create-generic-issue`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| ctx.jira.project_key (from client config) | - | - |
| ctx.data["issue_type"] = str (e.g., "Story", "Bug", "Task") | - | - |
| ctx.data["issue_type_id"] = str (e.g., "10001") | - | - |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `select_issue_priority`

Select priority for the new issue from available priorities in Jira.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: select_issue_priority
```

**Used by built-in workflows:** `create-generic-issue`

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `ai_enhance_issue_description`

Use AI to generate title and enhance the brief description into a detailed description.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: ai_enhance_issue_description
```

**Used by built-in workflows:** `create-generic-issue`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| ctx.data["brief_description"] | - | - |
| ctx.data["issue_type"] | - | - |
| ctx.data["title"] = str (generated by AI) | - | - |
| ctx.data["enhanced_description"] = str | - | - |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `review_issue_description`

Review and optionally edit the enhanced description.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: review_issue_description
```

**Used by built-in workflows:** `create-generic-issue`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| ctx.data["enhanced_description"] | - | - |
| ctx.data["final_description"] = str | - | - |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `confirm_assignee_for_new_issue`

Ask if the issue about to be created should be self-assigned.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: confirm_assignee_for_new_issue
```

**Used by built-in workflows:** `create-generic-issue`

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |

### `create_generic_issue`

Create the issue in Jira.

**How to read this contract**

- `Inputs (from ctx.data)` shows what the step expects before it runs.
- `Outputs (saved to ctx.data)` shows the metadata keys later steps can read after `Success` or `Skip`.
- `Returns` describes the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate function return payload.

**Workflow usage**

```yaml
- plugin: jira
  step: create_generic_issue
```

**Used by built-in workflows:** `create-generic-issue`

**Requires**

| Name | Type | Description |
|------|------|-------------|
| ctx.data["title"] | - | - |
| ctx.data["final_description"] | - | - |
| ctx.data["issue_type"] | - | - |
| ctx.data["priority"] | - | - |
| ctx.data["auto_assign"] (bool) | - | - |
| ctx.data["assignee_id"] (optional, if auto_assign is True) | - | - |
| ctx.data["created_issue"] = UIJiraIssue | - | - |

**Returns**

| Result | Saved for later steps | Description |
|--------|-----------------------|-------------|
| `WorkflowResult` | - | - |
