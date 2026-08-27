# Jira Plugin

The Jira plugin provides Titan's Jira integration for issue lookup, JQL search, transitions, versions, and AI-assisted issue workflows. It exposes:

- a high-level `JiraClient` for direct use from Titan code
- reusable workflow `steps` for issue search, issue analysis, transitions, and issue creation
- built-in workflows such as `analyze-jira-issues`, `create-generic-issue`, and `plan-jira-issue`

## Requirements

To use the Jira plugin in a project:

- Enable the `jira` plugin in `.titan/config.toml`
- Configure Jira connection settings such as `base_url` and `email`
- Store the Jira API token in Titan secrets
- Optionally configure a `default_project` so project-specific operations can work without passing a project key every time

Example project configuration:

```toml
[plugins.jira]
enabled = true

[plugins.jira.config]
base_url = "https://your-company.atlassian.net"
email = "developer@example.com"
default_project = "APP"
```

The API token is stored in secrets, not in the config file.

## Public surfaces

- [Client API](./client-api.md): direct Python methods exposed by `JiraClient`
- [Workflow Steps](./workflow-steps.md): public reusable workflow steps grouped by functionality
- [Built-in Workflows](./built-in-workflows.md): workflows shipped by the plugin

## Accessing the client

In Titan code, the public entry point is the Jira plugin client:

```python
jira_plugin = config.registry.get_plugin("jira")
client = jira_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

## Public workflow steps

The Jira plugin exposes public reusable steps for:

- search and interactive selection
- issue retrieval and AI analysis
- transitions and fix version automation
- guided issue creation

The complete grouped reference lives in [Workflow Steps](./workflow-steps.md).
