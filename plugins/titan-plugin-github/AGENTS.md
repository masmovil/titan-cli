# AGENTS.md - Titan GitHub Plugin

Documentation for AI coding agents working on the `titan-plugin-github`.

---

## 📋 Plugin Overview

**Titan GitHub Plugin** provides GitHub integration for the Titan CLI workflow engine. It allows for automating pull request creation, management, and other GitHub-related tasks.

**This plugin depends on the `titan-plugin-git` plugin.**

**Requires:**
- A `GITHUB_TOKEN` with repository access, managed by the `SecretManager`.
- The `git` command-line tool (a dependency of the `git` plugin).

---

## 📁 Project Structure

```
titan_plugin_github/
├── __init__.py
├── clients/
│   └── github_client.py   # Wrapper for the GitHub API
├── models.py              # Pydantic models for GitHub objects (PR, etc.)
├── exceptions.py          # Custom exceptions
├── plugin.py              # The GitHubPlugin definition
└── steps/
    ├── create_pr_step.py  # Workflow steps
    └── ...
```

---

## 🤖 Core Components

### `GitHubClient` (`clients/github_client.py`)

This is the main entry point for all GitHub API operations. It uses an HTTP client (like `httpx`) to make authenticated requests to the GitHub API.

**Key Methods:**
- `create_pull_request(...) -> PullRequest`: Creates a new pull request.
- `get_pull_request(...) -> PullRequest`: Retrieves details for a PR.
- `add_reviewers(...)`: Adds reviewers to a PR.

### `GitHubPlugin` (`plugin.py`)

This class is the entry point for the plugin system. It is responsible for:
- Declaring the plugin's `name` ("github").
- Declaring its `dependencies` (["git"]).
- Initializing the `GitHubClient` with the token from `SecretManager`.
- Providing the `GitHubClient` instance to the `WorkflowContextBuilder`.
- Exposing workflow steps via the `get_steps()` method.

### Workflow Steps (`steps/`)

Each file in this directory defines one or more `StepFunction`s that can be used in workflows.

**Example (`create_pr_step.py`):**
```python
from titan_cli.engine import WorkflowContext, Success, Error

def create_pr_step(ctx: WorkflowContext) -> Success:
    if not ctx.github:
        return Error("GitHub client is not available.")
    
    title = ctx.get("pr_title")
    if not title:
        return Error("Pull request title not found in context.")
    
    pr = ctx.github.create_pull_request(
        title=title,
        body=ctx.get("pr_body", ""),
        base=ctx.get("base_branch"),
        head=ctx.git.get_current_branch() # Uses git plugin client
    )
    
    return Success("Pull request created", metadata={"pull_request": pr})
```

---
## 🧪 Testing

Tests for this plugin are located in the `tests/` directory. To add a new test for a step or client method, create a new test function in `tests/test_github_plugin.py`.

Use `pytest` and `unittest.mock` to mock the `GitHubClient` and the dependent `GitClient` when testing steps in isolation.
