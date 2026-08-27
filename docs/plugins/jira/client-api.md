# Jira Client API

The Jira plugin adds Jira operations to Titan through a high-level client and reusable workflows. It covers issue lookup, JQL search, comments, transitions, issue creation, metadata discovery, links, and AI-assisted issue workflows.

This page documents the plugin from a functional point of view, while also showing how each capability is called and which parameters it needs.

---

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

---

## Accessing the client

In Titan code, the public entry point is the Jira plugin client:

```python
jira_plugin = config.registry.get_plugin("jira")
client = jira_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

---

## Issue operations

### Get an issue

Returns a single Jira issue by key.

**Call:**

```python
client.get_issue(key="APP-123", expand=["changelog"])
```

**Parameters:**

- `key`: Required. Issue key.
- `expand`: Optional. Extra Jira expansions to request.

### Search issues with JQL

Searches for issues using a JQL query.

**Call:**

```python
client.search_issues(
    jql='project = APP AND status = "To Do"',
    max_results=20,
    fields=["summary", "status", "assignee"],
)
```

**Parameters:**

- `jql`: Required. JQL query string.
- `max_results`: Optional. Maximum number of issues to return.
- `fields`: Optional. Fields to request from Jira.

### Create an issue

Creates a new Jira issue.

**Call:**

```python
client.create_issue(
    issue_type="Task",
    summary="Add server-side pagination",
    description="The results endpoint should support pagination.",
    project="APP",
    assignee="developer@example.com",
    labels=["backend", "api"],
    priority="High",
    fields={"components": [{"name": "Search"}]},
)
```

**Parameters:**

- `issue_type`: Required. Issue type name such as `Bug`, `Story`, or `Task`.
- `summary`: Required. Issue summary.
- `description`: Optional. Issue description.
- `project`: Optional. Project key. Uses the configured default project when omitted.
- `assignee`: Optional. Assignee username or email.
- `labels`: Optional. Labels to apply.
- `priority`: Optional. Priority name.
- `fields`: Optional. Additional Jira fields to merge into the payload.

### Create a subtask

Creates a subtask under an existing parent issue.

**Call:**

```python
client.create_subtask(
    parent_key="APP-123",
    summary="Add API tests",
    description="Cover pagination and empty-state cases.",
)
```

**Parameters:**

- `parent_key`: Required. Parent issue key.
- `summary`: Required. Subtask summary.
- `description`: Optional. Subtask description.

This operation requires a configured default project.

---

## Project operations

### Get a project

Returns a Jira project by key.

**Call:**

```python
client.get_project(key="APP")
```

**Parameters:**

- `key`: Optional. Project key. Uses the configured default project when omitted.

### List projects

Returns all Jira projects accessible to the current user.

**Call:**

```python
client.list_projects()
```

**Parameters:**

- No parameters.

---

## Comment operations

### Get issue comments

Returns the comments for a Jira issue.

**Call:**

```python
client.get_comments("APP-123")
```

**Parameters:**

- `issue_key`: Required. Issue key.

### Add a comment

Adds a comment to a Jira issue.

**Call:**

```python
client.add_comment("APP-123", "The API contract has been updated.")
```

**Parameters:**

- `issue_key`: Required. Issue key.
- `body`: Required. Comment text.

---

## Transition operations

### Get available transitions

Returns the transitions available for a Jira issue.

**Call:**

```python
client.get_transitions("APP-123")
```

**Parameters:**

- `issue_key`: Required. Issue key.

### Transition an issue

Moves an issue to another Jira status.

**Call:**

```python
client.transition_issue(
    issue_key="APP-123",
    new_status="In Progress",
    comment="Starting implementation.",
)
```

**Parameters:**

- `issue_key`: Required. Issue key.
- `new_status`: Required. Target status name.
- `comment`: Optional. Comment to add while transitioning.

---

## Metadata operations

### Get issue types

Returns the issue types available for a project.

**Call:**

```python
client.get_issue_types(project_key="APP")
```

**Parameters:**

- `project_key`: Optional. Project key. Uses the configured default project when omitted.

### List project statuses

Returns the statuses available for a project.

**Call:**

```python
client.list_statuses(project_key="APP")
```

**Parameters:**

- `project_key`: Optional. Project key. Uses the configured default project when omitted.

### Get the current Jira user

Returns information about the authenticated Jira user.

**Call:**

```python
client.get_current_user()
```

**Parameters:**

- No parameters.

### List project versions

Returns the versions configured for a project.

**Call:**

```python
client.list_project_versions(project_key="APP")
```

**Parameters:**

- `project_key`: Optional. Project key. Uses the configured default project when omitted.

### Create a version

Creates a Jira version in a project.

**Call:**

```python
client.create_version(
    name="25.45",
    project_key="APP",
    description="Weekly mobile release",
    release_date="2026-04-30",
)
```

**Parameters:**

- `name`: Required. Version name.
- `project_key`: Optional. Project key. Uses the configured default project when omitted.
- `description`: Optional. Version description.
- `release_date`: Optional. Jira release date in `YYYY-MM-DD` format.

### Ensure a version exists

Returns an existing version by name or creates it if missing.

**Call:**

```python
client.ensure_version_exists(
    name="25.45",
    project_key="APP",
    description="Weekly mobile release",
)
```

**Parameters:**

- `name`: Required. Version name.
- `project_key`: Optional. Project key. Uses the configured default project when omitted.
- `description`: Optional. Description to use if the version must be created.
- `release_date`: Optional. Release date to use if the version must be created.

### Assign a fixVersion

Assigns a Jira fixVersion to an issue, by version ID or version name.

**Call:**

```python
client.assign_fix_version(
    issue_key="APP-123",
    version_name="25.45",
    project_key="APP",
)
```

**Parameters:**

- `issue_key`: Required. Issue key.
- `version_id`: Optional. Jira version ID.
- `version_name`: Optional. Version name. Required when `version_id` is not provided.
- `project_key`: Optional. Project key used to resolve `version_name`. Uses the configured default project when omitted.

### Assign an issue to a user

Assigns an existing issue to a user by account ID.

**Call:**

```python
client.assign_issue(
    issue_key="APP-123",
    account_id="5b10a2844c20165700ede21g",
)
```

**Parameters:**

- `issue_key`: Required. Issue key.
- `account_id`: Required. Jira account ID of the user to assign (e.g. from `client.get_current_user()`).

### Get priorities

Returns the priorities available in Jira.

**Call:**

```python
client.get_priorities()
```

**Parameters:**

- No parameters.

---

## Link operations

### Link two issues

Creates a Jira link between two issues.

**Call:**

```python
client.link_issue(
    inward_issue="APP-123",
    outward_issue="APP-456",
    link_type="Relates",
)
```

**Parameters:**

- `inward_issue`: Required. Source issue key.
- `outward_issue`: Required. Target issue key.
- `link_type`: Optional. Jira link type.

### Add a remote link

Adds an external link, such as a pull request or document, to a Jira issue.

**Call:**

```python
client.add_remote_link(
    issue_key="APP-123",
    url="https://example.com/pull/123",
    title="Pull Request 123",
    relationship="relates to",
)
```

**Parameters:**

- `issue_key`: Required. Issue key.
- `url`: Required. External URL to link.
- `title`: Required. Link title.
- `relationship`: Optional. Relationship description.

---

## Related workflows

The Jira plugin ships with workflows that use these capabilities directly:

- `analyze-jira-issues`: Searches open issues, lets the user select one, and analyzes it with AI
- `create-generic-issue`: Guides the user through issue creation, enhances the content with AI, and creates the Jira issue

These workflows can be used as-is or extended from `.titan/workflows/`.
