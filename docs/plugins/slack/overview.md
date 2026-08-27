# Slack Plugin

The Slack plugin provides Titan's Slack integration for repo-scoped Slack App configuration, personal user authentication, workspace validation, discovery, messaging, and conversation summaries.

It exposes:

- a public `SlackClient`
- reusable workflow steps
- one built-in workflow for channel summaries

## Requirements

To use the Slack plugin in a project:

- Enable the `slack` plugin in `.titan/config.toml`
- Configure Slack through Titan's Slack-specific configuration screen
- Complete the BYO Slack App + PKCE flow
- Store the resulting personal Slack token in keyring for the active Titan project

Example project configuration:

```toml
[plugins.slack]
enabled = true

[plugins.slack.config]
oauth_client_id = "1234567890.1234567890"
default_team_id = "T12345678"
default_team_name = "My Workspace"
granted_scopes = [
  "users:read",
  "channels:read",
  "channels:history",
  "groups:read",
  "groups:history",
  "im:history",
  "mpim:history",
  "chat:write",
  "im:write",
  "mpim:write",
  "channels:write",
  "groups:write",
]
default_channels = ["chapter-apps-android", "release-notes"]
```

Slack stores the personal access token, refresh token, and token-expiry metadata in keyring, not in the config file.
Project config stores shared non-secret Slack metadata such as workspace binding and granted scopes.

## Slack App Setup

Current setup expectations:

- Use your own Slack App
- Enable PKCE for the OAuth flow
- Configure this exact redirect URI in Slack:
  `http://127.0.0.1:8765/slack/callback`
- The redirect URI must match exactly, including host, port, and path
- `127.0.0.1` and `localhost` are different values for Slack OAuth

With PKCE enabled for localhost redirects, Slack may issue expiring user tokens together with refresh tokens. Titan refreshes these tokens automatically for the active project and persists the rotated secrets in keyring.

## Scope Snapshot

Titan currently requests these Slack scopes during OAuth:

- `users:read`
- `channels:read`
- `channels:history`
- `groups:read`
- `groups:history`
- `im:history`
- `mpim:history`
- `chat:write`
- `im:write`
- `mpim:write`
- `channels:write`
- `groups:write`

`granted_scopes` in project config is the scope snapshot recorded from the last successful OAuth connection.

## Public Surfaces

- [Client API](./client-api.md): direct Python methods exposed by `SlackClient`
- [Workflow Steps](./workflow-steps.md): public reusable workflow steps grouped by functionality
- [Built-in Workflows](./built-in-workflows.md): workflows shipped by the plugin
- `SlackFormatter` (`titan_plugin_slack.formatting`): stateless text formatting toolkit (see below)

## Accessing the Client

```python
slack_plugin = config.registry.get_plugin("slack")
client = slack_plugin.get_client()
```

## Public Workflow Steps

The Slack plugin currently exposes public reusable steps for:

- validating the current Slack connection
- listing visible users and public channels
- selecting Slack users or channels as workflow targets
- preparing a message destination and posting messages
- resolving a conversation, reading recent messages, and summarizing them with AI

## Built-in Workflows

The Slack plugin currently ships one built-in workflow:

- `summarize-slack-target`

Other Slack capabilities remain available as public reusable steps for composition from project workflows or other plugin workflows.

## Message Formatting

Slack messages sent through `chat.postMessage` render `mrkdwn`, not standard Markdown: bold uses a single asterisk (`*bold*`), there is no header syntax, and there is no native table support. `SlackFormatter` converts standard Markdown (e.g. AI-generated text) into Slack's mrkdwn, so the same source content can also be rendered as normal Markdown elsewhere (like the Titan TUI).

```python
from titan_plugin_slack.formatting import SlackFormatter

# Convert a full Markdown document (headers, bold/italic/strikethrough,
# links, bullet lists, and pipe tables) into Slack mrkdwn.
slack_text = SlackFormatter.to_mrkdwn(markdown_summary)

# Or build a Slack-friendly table directly from row data.
table_text = SlackFormatter.table(
    rows=[["titan-cli", "0.6.0"], ["ragnarok", "0.9.3"]],
    headers=["Plugin", "Version"],
)
```

Both methods are stateless and can be called from any step, project workflow, or personal script — no plugin registration required.
