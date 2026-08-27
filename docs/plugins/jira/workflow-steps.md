# Jira Workflow Steps

The Jira plugin exposes public reusable workflow steps through `JiraPlugin.get_steps()`. The reference groups them by workflow intent so teams can discover related Jira building blocks quickly.

For full contract details for every public step, including documented inputs, outputs, and return behavior, see the [detailed step reference](../generated/jira-step-reference.md).

## Functional groups

- [Search and Selection](#search-and-selection)
- [Issue Retrieval and Analysis](#issue-retrieval-and-analysis)
- [Transitions and Fix Versions](#transitions-and-fix-versions)
- [Issue Creation](#issue-creation)

## Summary

| Step | Group | Used by built-in workflows |
|------|-------|----------------------------|
| `search_saved_query` | Search and Selection | `analyze-jira-issues` |
| `search_jql` | Search and Selection | - |
| `prompt_select_issue` | Search and Selection | `analyze-jira-issues` |
| `get_issue` | Issue Retrieval and Analysis | - |
| `ai_analyze_issue_requirements` | Issue Retrieval and Analysis | `analyze-jira-issues` |
| `get_transitions` | Transitions and Fix Versions | - |
| `transition_issue` | Transitions and Fix Versions | - |
| `verify_issue_state` | Transitions and Fix Versions | - |
| `list_versions` | Transitions and Fix Versions | - |
| `create_version` | Transitions and Fix Versions | - |
| `ensure_version_exists` | Transitions and Fix Versions | - |
| `assign_fix_version` | Transitions and Fix Versions | - |
| `verify_issue_has_fix_version` | Transitions and Fix Versions | - |
| `prompt_issue_description` | Issue Creation | `create-generic-issue` |
| `select_issue_type` | Issue Creation | `create-generic-issue` |
| `select_issue_priority` | Issue Creation | `create-generic-issue` |
| `ai_enhance_issue_description` | Issue Creation | `create-generic-issue` |
| `review_issue_description` | Issue Creation | `create-generic-issue` |
| `confirm_assignee_for_new_issue` | Issue Creation | `create-generic-issue` |
| `create_generic_issue` | Issue Creation | `create-generic-issue` |

## Search and Selection

Use these steps to query Jira and let the user choose the issue that the workflow should act on.

- `search_saved_query`: search Jira issues using a named saved query
- `search_jql`: search Jira issues using explicit JQL from workflow context
- `prompt_select_issue`: prompt the user to choose one issue from the search results

## Issue Retrieval and Analysis

Use these steps to retrieve full issue details and produce AI-assisted requirement analysis.

- `get_issue`: fetch full Jira issue details for a selected issue
- `ai_analyze_issue_requirements`: generate an AI-assisted requirements analysis for the selected issue

## Transitions and Fix Versions

Use these steps to inspect transitions, move issues, and manage fix-version data.

- `get_transitions`: load the transitions available for an issue
- `transition_issue`: move an issue to another Jira state
- `verify_issue_state`: check that an issue is already in the expected state
- `list_versions`: list versions available for the current Jira project
- `create_version`: create a Jira version
- `ensure_version_exists`: create a version only when it does not already exist
- `assign_fix_version`: assign a fix version to an issue
- `verify_issue_has_fix_version`: verify that an issue already has the expected fix version

## Issue Creation

Use these steps to guide a user from a rough request to a created Jira issue.

- `prompt_issue_description`: capture a brief user description for the new issue
- `select_issue_type`: choose the Jira issue type for the new issue
- `select_issue_priority`: choose the Jira issue priority
- `ai_enhance_issue_description`: expand the raw request into title and description using AI
- `review_issue_description`: review and optionally edit the generated issue content
- `confirm_assignee_for_new_issue`: ask whether the new issue should be self-assigned
- `create_generic_issue`: create the Jira issue from the prepared workflow context

<!-- BEGIN GENERATED STEP CONTRACTS -->
## Detailed Step Contracts

The summaries above show what each jira step is for. The sections below show the documented contract for each public step: what it expects from `ctx.data`, what it saves back, and what result types it may return.

Expand a step to see its workflow usage, required context, inputs, outputs, and result behavior.

How to read these contracts:

- `Inputs (from ctx.data)` = values the step expects before it runs.
- `Outputs (saved to ctx.data)` = metadata keys saved for later steps when the step returns `Success` or `Skip`.
- `Returns` = the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate payload.

### Search and Selection

??? info "`search_saved_query`"
    Search JIRA issues using a saved query.

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


??? info "`search_jql`"
    Search JIRA issues using a custom JQL query.

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


??? info "`prompt_select_issue`"
    Prompt user to select a JIRA issue from search results.

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


??? info "`select_jira_issue`"
    Resolve a JIRA issue key from user input: a plain number, a full key, or a board search.

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

    **Inputs (from ctx.data)**

    None documented.

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


### Issue Retrieval and Analysis

??? info "`get_issue`"
    Get JIRA issue details by key.

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


??? info "`get_comments`"
    Get all comments for a JIRA issue.

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


??? info "`ai_analyze_issue_requirements`"
    Analyze JIRA issue requirements using AI.

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


### AI Planning Handoff

??? info "`build_jira_task_context`"
    Build the full AI prompt for planning work on a JIRA issue.

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


??? info "`confirm_and_assign_issue`"
    Ask the user if they want to assign the current JIRA issue to themselves, and do it.

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


### Transitions and Fix Versions

??? info "`get_transitions`"
    Fetch available transitions for a Jira issue.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: get_transitions
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If transitions are fetched successfully. |
    | `Error` | - | If required context is missing or the Jira call fails. |


??? info "`transition_issue`"
    Transition a Jira issue to a target status.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: transition_issue
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the issue transitions successfully. |
    | `Error` | - | If required context is missing or the Jira call fails. |


??? info "`verify_issue_state`"
    Verify that a Jira issue is currently in the expected status.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: verify_issue_state
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the issue is in the expected status. |
    | `Error` | - | If required context is missing, verification fails, or the Jira call fails. |


??? info "`list_versions`"
    List unreleased versions for a JIRA project.

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


??? info "`create_version`"
    Create a Jira version.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: create_version
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the version is created successfully. |
    | `Error` | - | If required context is missing or the Jira call fails. |


??? info "`ensure_version_exists`"
    Ensure a Jira version exists, creating it if missing.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: ensure_version_exists
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the version already exists or is created successfully. |
    | `Error` | - | If required context is missing or the Jira call fails. |


??? info "`assign_fix_version`"
    Assign a fixVersion to a Jira issue.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: assign_fix_version
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the fix version is assigned successfully. |
    | `Error` | - | If required context is missing or the Jira call fails. |


??? info "`verify_issue_has_fix_version`"
    Verify a Jira issue has the expected fixVersion.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: verify_issue_has_fix_version
    ```

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the issue has the expected fix version. |
    | `Error` | - | If required context is missing, verification fails, or the Jira call fails. |


### Issue Creation

??? info "`prompt_issue_description`"
    Prompt user for brief description of the issue.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: prompt_issue_description
    ```

    **Used by built-in workflows:** `create-generic-issue`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`select_issue_type`"
    Select issue type for the new issue.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`select_issue_priority`"
    Select priority for the new issue from available priorities in Jira.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: select_issue_priority
    ```

    **Used by built-in workflows:** `create-generic-issue`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`ai_enhance_issue_description`"
    Use AI to generate title and enhance the brief description into a detailed description.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`review_issue_description`"
    Review and optionally edit the enhanced description.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`confirm_assignee_for_new_issue`"
    Ask if the issue about to be created should be self-assigned.

    **Workflow usage**

    ```yaml
    - plugin: jira
      step: confirm_assignee_for_new_issue
    ```

    **Used by built-in workflows:** `create-generic-issue`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |


??? info "`create_generic_issue`"
    Create the issue in Jira.

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

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `WorkflowResult` | - | - |
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
