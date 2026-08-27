# Slack Built-in Workflows

The Slack plugin currently ships two built-in workflows.

## `summarize-slack-target`

Search for a person or channel, read recent Slack messages, and summarize them with AI.

**Source workflow:** `plugins/titan-plugin-slack/titan_plugin_slack/workflows/summarize-slack-target.yaml`

### Default flow

1. `slack.validate_connection`
2. `slack.select_target`
3. `slack.ensure_target_conversation`
4. `slack.read_recent_messages`
5. `slack.ai_summarize_messages`

### Typical usage

- summarize a recent DM or channel without manually browsing the Slack UI
- search Slack once and pick either a person or a channel from the same result list

### Scope constraints

- this workflow depends on conversation-history scopes and AI configuration
- it assumes one active Slack workspace binding for the current repository
- it searches both users and channels through `select_target` and does not offer a quick-pick shortcut for repository-configured `default_channels` (use `select_default_or_search_channel_target` directly in a custom workflow if that shortcut is needed)

### Related public steps

- `validate_connection`
- `select_target`
- `ensure_target_conversation`
- `read_recent_messages`
- `ai_summarize_messages`

## `post-message`

Resolve a Slack target and post a message, meant to be called as a nested `workflow:` step from any other workflow (project, personal, or another plugin's).

**Source workflow:** `plugins/titan-plugin-slack/titan_plugin_slack/workflows/post-message.yaml`

### Default flow

1. `slack.validate_connection`
2. `slack.select_default_or_search_channel_target`
3. `slack.prepare_message_destination`
4. `slack.prompt_message_body`
5. `slack.format_markdown_message`
6. `slack.post_message`

### Typical usage

Call it as a nested step, sharing `ctx.data` with the caller:

```yaml
- id: post_summary_to_slack
  name: "Post Summary to Slack"
  workflow: "plugin:slack/post-message"
  on_error: continue   # treat this as an optional extra; a caller should never fail because of it
```

Before calling it, a caller can optionally set:

- `slack_message_text` (str): already Slack-ready text (e.g. a prebuilt table). Used verbatim, never converted.
- `slack_message_markdown` (str): standard Markdown text. Converted to Slack mrkdwn by `format_markdown_message`.
- `slack_preferred_target` (str): a person or channel name to auto-select with no prompt, when it resolves to exactly one match.

If neither `slack_message_text` nor `slack_message_markdown` is set, `prompt_message_body` asks the user to type a message interactively - that typed text is then converted the same way a caller-provided Markdown message would be.

### Scope constraints

- always call it with `on_error: continue` on the outer `workflow:` step - it's designed to fail cleanly (missing Slack plugin, not configured, cancelled selection) without ever being the reason a caller workflow fails
- this workflow depends on messaging scopes (`chat:write`, etc.) and, for `select_default_or_search_channel_target`'s search fallback, conversation-listing scopes

### Related public steps

- `validate_connection`
- `select_default_or_search_channel_target`
- `prepare_message_destination`
- `prompt_message_body`
- `format_markdown_message`
- `post_message`
