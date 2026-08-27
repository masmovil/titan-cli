# GitHub Workflow Steps

The GitHub plugin exposes public reusable workflow steps through `GitHubPlugin.get_steps()`. The reference groups them by user-facing functionality so workflow authors can find related building blocks quickly.

For full contract details for every public step, including documented inputs, outputs, and return behavior, see the [detailed step reference](../generated/github-step-reference.md).

## Functional groups

- [Pull Requests](#pull-requests)
- [Prompt and Selection](#prompt-and-selection)
- [Issue Creation](#issue-creation)
- [Pull Request Review](#pull-request-review)
- [Code Review](#code-review)
- [Worktree Support](#worktree-support)

## Summary

| Step | Group | Used by built-in workflows |
|------|-------|----------------------------|
| `create_pr` | Pull Requests | `create-pr-ai` |
| `get_pull_request` | Pull Requests | - |
| `merge_pull_request` | Pull Requests | - |
| `verify_pull_request_state` | Pull Requests | - |
| `ai_suggest_pr_description` | Pull Requests | `create-pr-ai` |
| `prompt_for_pr_title` | Prompt and Selection | - |
| `prompt_for_pr_body` | Prompt and Selection | - |
| `prompt_for_issue_body_step` | Prompt and Selection | `create-issue-ai` |
| `prompt_for_self_assign` | Prompt and Selection | `create-issue-ai` |
| `prompt_for_labels` | Prompt and Selection | - |
| `select_cli` | Prompt and Selection | - |
| `ai_suggest_issue_title_and_body` | Issue Creation | `create-issue-ai` |
| `preview_and_confirm_issue` | Issue Creation | - |
| `create_issue` | Issue Creation | `create-issue-ai` |
| `select_pr_for_review` | Pull Request Review | `respond-pr-comments` |
| `fetch_pending_comments` | Pull Request Review | `respond-pr-comments` |
| `check_clean_state` | Pull Request Review | `respond-pr-comments` |
| `checkout_pr_branch` | Pull Request Review | `respond-pr-comments` |
| `review_comments` | Pull Request Review | `respond-pr-comments` |
| `push_commits` | Pull Request Review | `respond-pr-comments` |
| `send_comment_replies` | Pull Request Review | `respond-pr-comments` |
| `request_review` | Pull Request Review | `respond-pr-comments` |
| `checkout_original_branch` | Pull Request Review | `respond-pr-comments` |
| `select_pr_for_code_review` | Code Review | - |
| `fetch_pr_review_bundle` | Code Review | - |
| `build_change_manifest` | Code Review | - |
| `build_existing_comments_index` | Code Review | - |
| `build_review_checklist` | Code Review | - |
| `ai_review_plan` | Code Review | - |
| `validate_review_plan` | Code Review | - |
| `resolve_review_context` | Code Review | - |
| `ai_review_findings` | Code Review | - |
| `normalize_findings` | Code Review | - |
| `dedupe_findings` | Code Review | - |
| `build_new_comment_actions` | Code Review | - |
| `validate_review_actions` | Code Review | - |
| `submit_review_actions` | Code Review | - |
| `build_thread_review_candidates` | Code Review | - |
| `build_thread_review_contexts` | Code Review | - |
| `ai_thread_resolution` | Code Review | - |
| `normalize_thread_decisions` | Code Review | - |
| `build_thread_actions` | Code Review | - |
| `create_worktree` | Worktree Support | - |
| `cleanup_worktree` | Worktree Support | - |

## Pull Requests

Use these steps to generate PR content, inspect PR state, and create or merge pull requests.

- `create_pr`: create a pull request from workflow context data
- `get_pull_request`: fetch a pull request and expose it to later steps
- `merge_pull_request`: merge a pull request with workflow-selected merge options
- `verify_pull_request_state`: validate that a pull request is in the expected state
- `ai_suggest_pr_description`: generate PR title and body from branch changes using AI

## Prompt and Selection

Use these steps when a workflow needs interactive user input before creation or review work starts.

- `prompt_for_pr_title`: capture a PR title interactively when one is not already available
- `prompt_for_pr_body`: capture a PR body interactively when one is not already available
- `prompt_for_issue_body_step`: capture the raw issue request before AI expansion
- `prompt_for_self_assign`: ask whether the current user should be assigned to the issue
- `prompt_for_labels`: prompt for labels to attach to an issue or PR
- `select_cli`: choose which external CLI a workflow should use

## Issue Creation

Use these steps to build and submit GitHub issues.

- `ai_suggest_issue_title_and_body`: generate issue content and suggested labels from user input
- `preview_and_confirm_issue`: show generated issue content and ask for explicit confirmation
- `create_issue`: create the final GitHub issue from workflow context data

## Pull Request Review

Use these steps for the contributor flow of responding to PR comments and restoring local branch state afterward.

- `select_pr_for_review`: select a pull request that needs comment response work
- `fetch_pending_comments`: load unresolved PR comments into workflow context
- `check_clean_state`: ensure the current branch is safe to leave before checkout
- `checkout_pr_branch`: switch to the PR branch while preserving original branch context
- `review_comments`: guide the user through resolving comments and making local changes
- `push_commits`: push local follow-up commits back to the PR branch
- `send_comment_replies`: submit replies for the reviewed comments
- `request_review`: request another review after follow-up work is pushed
- `checkout_original_branch`: restore the original branch after review work completes

## Code Review

These are advanced review-pipeline steps for structured AI-assisted code review. They are public and reusable, but many are intended to be composed together rather than used in isolation.

- `select_pr_for_code_review`: choose a PR for the advanced code-review pipeline
- `fetch_pr_review_bundle`: collect PR, diff, file, and discussion context for review
- `build_change_manifest`: build a structured manifest of changed files and targets
- `build_existing_comments_index`: index existing review comments to avoid duplicate findings
- `build_review_checklist`: prepare a review checklist from PR context
- `ai_review_plan`: ask AI to propose the review strategy
- `validate_review_plan`: verify that the AI review plan is structurally usable
- `resolve_review_context`: expand the exact contexts needed for targeted analysis
- `ai_review_findings`: run targeted AI analysis and produce candidate findings
- `normalize_findings`: normalize raw findings into workflow-friendly structures
- `dedupe_findings`: remove duplicate or overlapping findings before submission
- `build_new_comment_actions`: translate findings into GitHub review actions
- `validate_review_actions`: validate those review actions before posting
- `submit_review_actions`: submit review comments or review actions to GitHub
- `build_thread_review_candidates`: collect review threads that may need follow-up decisions
- `build_thread_review_contexts`: expand context needed to evaluate thread resolution
- `ai_thread_resolution`: ask AI whether open threads should be resolved or reopened
- `normalize_thread_decisions`: normalize thread resolution decisions for execution
- `build_thread_actions`: build GitHub actions from normalized thread decisions

## Worktree Support

Use these steps when a GitHub workflow should operate in a dedicated worktree.

- `create_worktree`: create an isolated worktree for GitHub-focused workflow tasks
- `cleanup_worktree`: remove a worktree created during workflow execution

<!-- BEGIN GENERATED STEP CONTRACTS -->
## Detailed Step Contracts

The summaries above show what each github step is for. The sections below show the documented contract for each public step: what it expects from `ctx.data`, what it saves back, and what result types it may return.

Expand a step to see its workflow usage, required context, inputs, outputs, and result behavior.

How to read these contracts:

- `Inputs (from ctx.data)` = values the step expects before it runs.
- `Outputs (saved to ctx.data)` = metadata keys saved for later steps when the step returns `Success` or `Skip`.
- `Returns` = the workflow result type (`Success`, `Skip`, `Error`, `Exit`), not a separate payload.

### Pull Requests

??? info "`create_pr`"
    Creates a GitHub pull request using data from the workflow context.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: create_pr
    ```

    **Used by built-in workflows:** `create-pr-ai`

    **Available to later steps:** `pr_number`, `pr_url`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |
    | `ctx.git` | - | An initialized GitClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_title` | str | The title of the pull request. |
    | `pr_body` | str, optional | The body/description of the pull request. |
    | `pr_head_branch` | str | The branch with the new changes. |
    | `pr_is_draft` | bool, optional | Whether to create the PR as a draft. Defaults to False. |
    | `pr_reviewers` | list, optional | List of GitHub usernames or team slugs to request review from. |
    | `pr_excluded_reviewers` | list, optional | List of GitHub usernames to exclude from team expansion. |
    | `pr_labels` | list, optional | List of label names to add to the PR. |
    | `auto_assign_prs` | bool | If True, automatically assigns the PR to the current GitHub user. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_number` | int | The number of the created pull request. |
    | `pr_url` | str | The URL of the created pull request. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_number`, `pr_url` | If the PR is created successfully. |
    | `Error` | - | If any required context arguments are missing or if the API call fails. |


??? info "`get_pull_request`"
    Fetch a pull request and store it in workflow context.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: get_pull_request
    ```

    **Available to later steps:** `pr_info`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_number` | int | Pull request number to fetch. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_info` | - | The fetched pull request object. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_info` | If the pull request is fetched successfully. |
    | `Error` | - | If required context is missing or the GitHub call fails. |


??? info "`merge_pull_request`"
    Merge a pull request using the configured GitHub client.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: merge_pull_request
    ```

    **Available to later steps:** `merge_result`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_number` | int | Pull request number to merge. |
    | `merge_method` | str, optional | Merge strategy. |
    | `commit_title` | str, optional | Override commit title. |
    | `commit_message` | str, optional | Override commit message. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `merge_result` | - | The GitHub merge result object. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `merge_result` | If the pull request is merged successfully. |
    | `Error` | - | If required context is missing or the GitHub call fails. |


??? info "`verify_pull_request_state`"
    Verify a pull request is currently in the expected state.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: verify_pull_request_state
    ```

    **Available to later steps:** `verified_pr_info`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_number` | int | Pull request number to inspect. |
    | `expected_state` | str | Expected pull request state. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `verified_pr_info` | - | The pull request object when verification succeeds. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `verified_pr_info` | If the pull request is in the expected state. |
    | `Error` | - | If required context is missing, verification fails, or the GitHub call fails. |


??? info "`ai_suggest_pr_description`"
    Generate PR title and description using PRAgent.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: ai_suggest_pr_description
    ```

    **Used by built-in workflows:** `create-pr-ai`

    **Available to later steps:** `pr_title`, `pr_body`, `pr_size`, `ai_generated`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.ai` | - | An initialized AIClient |
    | `ctx.git` | - | An initialized GitClient |
    | `ctx.github` | - | An initialized GitHubClient |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_head_branch` | str | The head branch for the PR |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_title` | str | AI-generated PR title |
    | `pr_body` | str | AI-generated PR description |
    | `pr_size` | str | Size classification (small/medium/large/very large) |
    | `ai_generated` | bool | True if AI generated the content |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_title`, `pr_body`, `pr_size`, `ai_generated` | PR description generated |
    | `Skip` | `pr_title`, `pr_body`, `pr_size`, `ai_generated` | AI not configured or user declined |
    | `Error` | - | Failed to generate PR description |


### Prompt and Selection

??? info "`prompt_for_pr_title`"
    Interactively prompts the user for a Pull Request title.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: prompt_for_pr_title
    ```

    **Available to later steps:** `pr_title`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI components. |

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_title` | str | The title entered by the user. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_title` | If the title was captured successfully. |
    | `Error` | - | If the user cancels or the title is empty. |
    | `Skip` | `pr_title` | If pr_title already exists. |


??? info "`prompt_for_pr_body`"
    Interactively prompts the user for a Pull Request body.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: prompt_for_pr_body
    ```

    **Available to later steps:** `pr_body`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI components. |

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_body` | str | The body/description entered by the user. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_body` | If the body was captured successfully. |
    | `Error` | - | If the user cancels. |
    | `Skip` | `pr_body` | If pr_body already exists. |


??? info "`prompt_for_issue_body_step`"
    Interactively prompts the user for a GitHub issue body.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: prompt_for_issue_body_step
    ```

    **Used by built-in workflows:** `create-issue-ai`

    **Available to later steps:** `issue_body`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI components. |

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue_body` | str | The body/description entered by the user. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `issue_body` | If the body was captured successfully. |
    | `Error` | - | If the user cancels. |
    | `Skip` | `issue_body` | If issue_body already exists. |


??? info "`prompt_for_self_assign`"
    Asks the user if they want to assign the issue to themselves.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: prompt_for_self_assign
    ```

    **Used by built-in workflows:** `create-issue-ai`

    **Available to later steps:** `assignees`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `assignees` | list[str] | Updated assignees list when the user chooses self-assignment. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `assignees` | If the assignment preference is captured successfully. |
    | `Error` | - | If the GitHub client is unavailable or the prompt fails. |


??? info "`prompt_for_labels`"
    Prompts the user to select labels for the issue.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: prompt_for_labels
    ```

    **Available to later steps:** `labels`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `labels` | list[str] | Labels selected by the user. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `labels` | If label selection completes successfully. |
    | `Skip` | `labels` | If the repository has no labels. |
    | `Error` | - | If the GitHub client is unavailable or the prompt fails. |


??? info "`select_cli`"
    Ask user to explicitly choose which AI CLI to use for PR analysis.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: select_cli
    ```

    **Used by built-in workflows:** `review-pr`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success with the chosen CLI name stored in ctx.data` | - | - |


### Issue Creation

??? info "`ai_suggest_issue_title_and_body`"
    Use AI to suggest a title and description for a GitHub issue.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: ai_suggest_issue_title_and_body
    ```

    **Used by built-in workflows:** `create-issue-ai`

    **Available to later steps:** `issue_title`, `issue_body`, `issue_category`, `labels`

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue_body` | str | Raw issue request entered by the user. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue_title` | str | AI-generated or user-edited title. |
    | `issue_body` | str | AI-generated or user-edited body. |
    | `issue_category` | str | Detected issue category. |
    | `labels` | list[str] | Suggested labels for the issue. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `issue_title`, `issue_body`, `issue_category`, `labels` | If issue content is generated and accepted. |
    | `Skip` | `issue_title`, `issue_body`, `issue_category`, `labels` | If AI is unavailable or the user rejects the generated issue. |
    | `Error` | - | If required context is missing or generation fails. |


??? info "`preview_and_confirm_issue`"
    Show a preview of the AI-generated issue and ask for confirmation.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: preview_and_confirm_issue
    ```

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue_title` | str | Generated issue title. |
    | `issue_body` | str | Generated issue body. |

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | If the user confirms the issue preview. |
    | `Error` | - | If required context is missing, the user rejects, or the prompt is cancelled. |


??? info "`create_issue`"
    Create a new GitHub issue.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: create_issue
    ```

    **Used by built-in workflows:** `create-issue-ai`

    **Available to later steps:** `issue`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.github` | - | An initialized GitHubClient. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue_title` | str | Issue title. |
    | `issue_body` | str | Issue body. |
    | `assignees` | list, optional | Usernames to assign. |
    | `labels` | list, optional | Labels to apply. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `issue` | GitHubIssue | The created issue object. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `issue` | If the issue is created successfully. |
    | `Error` | - | If required context is missing or the GitHub call fails. |


### Pull Request Review

??? info "`select_pr_for_review`"
    Select a PR from the user's open PRs to review comments.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: select_pr_for_review
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Available to later steps:** `selected_pr_number`, `selected_pr_title`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `selected_pr_number` | int | The selected PR number |
    | `selected_pr_title` | str | The selected PR title |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `selected_pr_number`, `selected_pr_title` | PR selected successfully |
    | `Exit` | - | No PRs available or user cancelled |
    | `Error` | - | Failed to fetch PRs |


??? info "`fetch_pending_comments`"
    Fetch unresolved review threads for the selected PR using GraphQL.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: fetch_pending_comments
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Available to later steps:** `review_threads`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `review_threads` | List[UICommentThread] | Unresolved review threads |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `review_threads` | Threads fetched |
    | `Exit` | - | No unresolved threads |
    | `Error` | - | Failed to fetch threads |


??? info "`check_clean_state`"
    Check that the working tree is clean before checking out the PR branch.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: check_clean_state
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Working tree is clean |
    | `Exit` | - | Uncommitted changes detected — user must stash manually |
    | `Error` | - | Failed to check status |


??? info "`checkout_pr_branch`"
    Save the current branch and checkout the PR branch.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: checkout_pr_branch
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Available to later steps:** `original_branch`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `original_branch` | str | Branch to restore after review |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `original_branch` | PR branch checked out |
    | `Error` | - | Failed to fetch or checkout |


??? info "`review_comments`"
    Review all unresolved comment threads one by one and take action.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: review_comments
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | All threads processed |
    | `Error` | - | Failed to process threads |


??? info "`push_commits`"
    Push commits to PR branch.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: push_commits
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Available to later steps:** `push_successful`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `push_successful` | bool | Whether push succeeded |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `push_successful` | Commits pushed |
    | `Skip` | `push_successful` | No commits to push or user cancelled |
    | `Error` | - | Failed to push |


??? info "`send_comment_replies`"
    Send comment replies (both text responses and commit hashes).

    **Workflow usage**

    ```yaml
    - plugin: github
      step: send_comment_replies
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Replies sent |
    | `Skip` | - | No replies to send or user cancelled |
    | `Error` | - | Failed to send replies |


??? info "`request_review`"
    Re-request review from existing reviewers.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: request_review
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Review re-requested |
    | `Skip` | - | Push didn't succeed or user cancelled |
    | `Error` | - | Failed to request review |


??? info "`checkout_original_branch`"
    Restore the original branch after PR review.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: checkout_original_branch
    ```

    **Used by built-in workflows:** `respond-pr-comments`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Restored to original branch |
    | `Exit` | - | No original branch saved or checkout failed |


### Code Review

??? info "`select_pr_for_code_review`"
    List all open PRs and ask user to select one.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: select_pr_for_code_review
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_pr_number`, `review_pr_title`, `review_pr_head`, `review_pr_base`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `review_pr_number` | int | Selected PR number |
    | `review_pr_title` | str | PR title |
    | `review_pr_head` | str | Head branch |
    | `review_pr_base` | str | Base branch |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Exit (no PRs or cancelled), or Error` | - | - |


??? info "`fetch_pr_review_bundle`"
    Fetch all data needed for a full PR review cycle.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: fetch_pr_review_bundle
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_pr`, `review_diff`, `review_changed_files`, `review_changed_files_with_stats`, `review_commit_sha`, `review_threads`, `review_general_comments`, `pr_template`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `review_pr` | UIPullRequest | Pull request details |
    | `review_diff` | str | Full unified diff |
    | `review_changed_files` | List[str] | Changed file paths (may be subset for large PRs) |
    | `review_changed_files_with_stats` | List[UIFileChange] | All files with add/del stats |
    | `review_commit_sha` | str | Head commit SHA |
    | `review_threads` | List[UICommentThread] | Inline review threads (unresolved) |
    | `review_general_comments` | List[UICommentThread] | General PR-level comments |
    | `pr_template` | str | None | PR template content if available |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (empty diff), or Error` | - | - |


??? info "`build_change_manifest`"
    Build a structured manifest of the PR changes (no AI involved).

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_change_manifest
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `change_manifest`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `change_manifest` | ChangeManifest | Structured PR context |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`build_existing_comments_index`"
    Build a compact index of existing PR comments for deduplication.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_existing_comments_index
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `existing_comments_index (List[ExistingCommentIndexEntry])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | existing_comments_index (List[ExistingCommentIndexEntry]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `existing_comments_index (List[ExistingCommentIndexEntry])` | - |


??? info "`classify_pr`"
    Classify PR size and composition before planning.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: classify_pr
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `pr_classification`, `review_profile`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI context. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `change_manifest` | ChangeManifest | Structured PR change summary. |
    | `existing_comments_index` | List[ExistingCommentIndexEntry], optional | Existing comments used to estimate review activity. |
    | `review_threads` | List[UICommentThread], optional | Current review threads. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_classification` | PRClassification | Deterministic PR classification. |
    | `review_profile` | ReviewProfile | Resolved review profile used during classification. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `pr_classification`, `review_profile` | When PR classification is computed successfully. |
    | `Error` | - | When required context is missing or the step cannot run. |


??? info "`score_review_candidates`"
    Rank changed files and precompute excluded files.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: score_review_candidates
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_profile`, `review_candidates`, `excluded_review_files`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI context. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `change_manifest` | ChangeManifest | Structured PR change summary. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `review_profile` | ReviewProfile | Resolved review profile used during scoring. |
    | `review_candidates` | List[ScoredReviewCandidate] | Ranked review candidates. |
    | `excluded_review_files` | List[ExcludedFileEntry] | Files excluded from deep review. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `review_profile`, `review_candidates`, `excluded_review_files` | When review candidates are scored successfully. |
    | `Exit` | - | When no reviewable candidates remain after exclusions. |
    | `Error` | - | When required context is missing or the step cannot run. |


??? info "`build_review_checklist`"
    Assemble the review checklist for this PR.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_review_checklist
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_checklist (List[ReviewChecklistItem])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | review_checklist (List[ReviewChecklistItem]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `review_checklist (List[ReviewChecklistItem])` | - |


??? info "`select_review_strategy`"
    Choose review strategy based on deterministic PR classification.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: select_review_strategy
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_strategy`

    **Requires**

    | Name | Type | Description |
    |------|------|-------------|
    | `ctx.textual` | - | Textual UI context. |

    **Inputs (from ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `pr_classification` | PRClassification | Deterministic PR classification. |

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `review_strategy` | ReviewStrategy | Execution strategy for planning and findings. |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `review_strategy` | When a review strategy is selected successfully. |
    | `Error` | - | When required context is missing or the step cannot run. |


??? info "`ai_review_plan`"
    First AI call: decide which files to read and which checklist items apply.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: ai_review_plan
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_plan (ReviewPlan)`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | review_plan (ReviewPlan) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`validate_review_plan`"
    Validate the AI-generated ReviewPlan against local semantic rules.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: validate_review_plan
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `validated_review_plan`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `validated_review_plan` | ReviewPlan | Same plan if valid |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error (halts workflow on validation failure)` | - | - |


??? info "`resolve_review_context`"
    Fetch the exact code context according to the validated review plan.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: resolve_review_context
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_context_package (ReviewContextPackage)`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | review_context_package (ReviewContextPackage) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`ai_review_findings`"
    Second AI call: find actionable problems in the exact code context.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: ai_review_findings
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `raw_findings`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `raw_findings` | list | str | Raw AI output before normalization |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`normalize_findings`"
    Parse and validate raw AI output into Finding models.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: normalize_findings
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `normalized_findings`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `normalized_findings` | List[Finding] | Validated Finding objects |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`dedupe_findings`"
    Remove findings that duplicate existing PR comments.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: dedupe_findings
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `deduped_findings`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `deduped_findings` | List[Finding] | Findings after duplicate removal |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`build_new_comment_actions`"
    Convert deduplicated findings into ReviewActionProposal objects.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_new_comment_actions
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `review_action_proposals (List[ReviewActionProposal])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | review_action_proposals (List[ReviewActionProposal]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Skip (no findings)` | - | - |


??? info "`validate_review_actions`"
    Present each ReviewActionProposal to the user for approval, editing, or skipping.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: validate_review_actions
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `approved_action_proposals (List[ReviewActionProposal])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | approved_action_proposals (List[ReviewActionProposal]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (none approved), or Error` | - | - |


??? info "`submit_review_actions`"
    Submit approved ReviewActionProposal objects to GitHub.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: submit_review_actions
    ```

    **Used by built-in workflows:** `review-pr`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (no approved actions), or Error` | - | - |


??? info "`build_thread_review_candidates`"
    Select open inline threads worth AI analysis.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_thread_review_candidates
    ```

    **Available to later steps:** `thread_review_candidates (List[ThreadReviewCandidate])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | thread_review_candidates (List[ThreadReviewCandidate]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (no candidates), or Error` | - | - |


??? info "`build_thread_review_contexts`"
    Enrich thread candidates with diff hunk context and full reply history.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_thread_review_contexts
    ```

    **Available to later steps:** `thread_review_contexts (List[ThreadReviewContext])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | thread_review_contexts (List[ThreadReviewContext]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (no candidates), or Error` | - | - |


??? info "`ai_thread_resolution`"
    AI call: decide what to do with each open thread.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: ai_thread_resolution
    ```

    **Available to later steps:** `raw_thread_decisions`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `raw_thread_decisions` | list | Raw AI output before normalization |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`normalize_thread_decisions`"
    Parse and validate raw AI output into ThreadDecision models.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: normalize_thread_decisions
    ```

    **Available to later steps:** `thread_decisions`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `thread_decisions` | List[ThreadDecision] | Validated ThreadDecision objects |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success or Error` | - | - |


??? info "`build_thread_actions`"
    Transform ThreadDecision objects into ReviewActionProposal objects.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: build_thread_actions
    ```

    **Available to later steps:** `review_action_proposals (List[ReviewActionProposal])`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | review_action_proposals (List[ReviewActionProposal]) | - | - |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success, Skip (no actionable decisions), or Error` | - | - |


### Worktree Support

??? info "`create_worktree`"
    Create a worktree for PR review.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: create_worktree
    ```

    **Used by built-in workflows:** `review-pr`

    **Available to later steps:** `worktree_path`, `worktree_created`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    | Name | Type | Description |
    |------|------|-------------|
    | `worktree_path` | str | Absolute path to worktree |
    | `worktree_created` | bool | Whether worktree was created |

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | `worktree_path`, `worktree_created` | Worktree created |
    | `Error` | - | Failed to create worktree |


??? info "`cleanup_worktree`"
    Cleanup a worktree created for PR review.

    **Workflow usage**

    ```yaml
    - plugin: github
      step: cleanup_worktree
    ```

    **Used by built-in workflows:** `review-pr`

    **Inputs (from ctx.data)**

    None documented.

    **Outputs (saved to ctx.data)**

    None documented.

    **Returns**

    | Result | Saved for later steps | Description |
    |--------|-----------------------|-------------|
    | `Success` | - | Worktree cleaned up |
    | `Exit` | - | No worktree to cleanup |
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
