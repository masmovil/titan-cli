# AGENTS.md - Titan Git Plugin

Documentation for AI coding agents working on the `titan-plugin-git`.

---

## 📋 Plugin Overview

**Titan Git Plugin** provides core Git functionalities to the Titan CLI workflow engine. It acts as a wrapper around the system's `git` command-line tool, offering a structured Python interface for common Git operations.

**This plugin has no dependencies on other Titan plugins.**

**Requires:** The `git` command-line tool must be installed and available in the system's `PATH`.

---

## 📁 Project Structure

```
titan_plugin_git/
├── __init__.py
├── clients/
│   └── git_client.py      # The Git CLI wrapper
├── models.py              # Pydantic models for Git objects (Status, Branch, etc.)
├── exceptions.py          # Custom exceptions
├── plugin.py              # The GitPlugin definition
└── steps/
    ├── status_step.py     # Workflow steps
    └── commit_step.py
```

---

## 🤖 Core Components

### `GitClient` (`clients/git_client.py`)

This is the main entry point for all Git operations. It uses `subprocess` to run `git` commands and parses their output into structured Python objects defined in `models.py`.

**Key Methods:**
- `get_status() -> GitStatus`: Returns the repository status.
- `get_current_branch() -> str`: Gets the current branch name.
- `checkout(branch: str)`: Switches to a different branch.
- `commit(message: str)`: Creates a commit.
- ...and many others.

### `GitPlugin` (`plugin.py`)

This class is the entry point for the plugin system. It is responsible for:
- Declaring the plugin's `name` ("git").
- Initializing the `GitClient`.
- Providing the `GitClient` instance to the `WorkflowContextBuilder`.
- Exposing the available workflow steps via the `get_steps()` method.

### Workflow Steps (`steps/`)

Each file in this directory defines one or more `StepFunction`s.

**Example (`status_step.py`):**
```python
from titan_cli.engine import WorkflowContext, Success, Error

def get_git_status_step(ctx: WorkflowContext) -> Success:
    if not ctx.git:
        return Error("Git client is not available.")
    
    status = ctx.git.get_status()
    return Success("Status retrieved", metadata={"git_status": status})
```

**Example (`commit_step.py`):**
```python
from titan_cli.engine import WorkflowContext, Success, Error

def create_git_commit_step(ctx: WorkflowContext) -> Success:
    message = ctx.get("commit_message")
    if not message:
        return Error("Commit message not found in context.")
    
    commit_hash = ctx.git.commit(message=message, all=ctx.get("all_files", False))
    return Success("Commit created", metadata={"commit_hash": commit_hash})
```

---
## 🧪 Testing

Tests for this plugin are located in the `tests/` directory. To add a new test for a step or client method, create a new test function in `tests/test_git_plugin.py`.

Use `pytest` and `unittest.mock` to mock the `GitClient` when testing steps in isolation.
