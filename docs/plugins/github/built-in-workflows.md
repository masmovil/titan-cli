# GitHub Built-in Workflows

The GitHub plugin ships reusable workflows for PR creation, issue creation, and PR comment response.

## `create-pr-ai`

Creates a pull request after preparing branch state, pushing changes, and generating PR content with AI.

Set `params.draft` to control draft behavior:

- `true`: create as draft without prompting
- `false`: create as ready for review without prompting
- `null`: ask interactively before creating the PR

**Source workflow:** `plugins/titan-plugin-github/titan_plugin_github/workflows/create-pr-ai.yaml`

### Default flow

1. nested workflow `commit-ai`
2. `git.push`
3. `git.get_current_branch`
4. `git.show_branch_diff_summary`
5. `before_pr_generation` hook
6. `github.ai_suggest_pr_description`
7. `github.prompt_for_pr_draft`
8. `github.prompt_for_labels` (configured to save into `pr_labels`)
9. `before_push` hook
10. `github.create_pr`
11. `after_pr` hook

### Hooks

- `before_pr_generation`: inject project-specific context before AI generates PR content
- `before_push`: run validations before PR creation
- `after_pr`: notify or trigger post-creation automation

## `create-issue-ai`

Prompts for issue context, generates issue title and body with AI, then creates the GitHub issue.

**Source workflow:** `plugins/titan-plugin-github/titan_plugin_github/workflows/create-issue-ai.yaml`

### Default flow

1. `github.prompt_for_issue_body_step`
2. `github.ai_suggest_issue_title_and_body`
3. `github.prompt_for_self_assign`
4. `github.create_issue`

## `respond-pr-comments`

Helps a contributor review pending PR comments, switch to the PR branch, apply changes, reply, and request another review.

**Source workflow:** `plugins/titan-plugin-github/titan_plugin_github/workflows/respond-pr-comments.yaml`

### Default flow

1. `github.select_pr_for_review`
2. `github.fetch_pending_comments`
3. `github.check_clean_state`
4. `github.checkout_pr_branch`
5. `github.review_comments`
6. `after_review` hook
7. `github.push_commits`
8. `github.send_comment_replies`
9. `github.request_review`
10. `github.checkout_original_branch`

### Hooks

- `after_review`: run lints, tests, or other checks before pushing replies

### Example extension

```yaml
extends: "plugin:github/respond-pr-comments"

hooks:
  after_review:
    - id: tests
      name: "Run Tests"
      command: "poetry run pytest"
      on_error: fail
```
