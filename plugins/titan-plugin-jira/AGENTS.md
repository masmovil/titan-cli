# AGENTS.md - Titan JIRA Plugin

Documentation for AI coding agents working on the `titan-plugin-jira`.

---

## 📋 Plugin Overview

**Titan JIRA Plugin** provides AI-powered JIRA integration to the Titan CLI workflow engine. It wraps the JIRA REST API, offering a structured Python interface for issue management, searching, and AI-powered requirements analysis.

**This plugin has no dependencies on other Titan plugins.**

**Requires:**
- A JIRA Server/Data Center instance with API access
- Personal Access Token (PAT) with appropriate permissions
- AI provider configured in Titan CLI (for AI analysis features)

---

## 📁 Project Structure

```
titan_plugin_jira/
├── __init__.py
├── clients/
│   └── jira_client.py         # JIRA REST API wrapper
├── models.py                  # Pydantic models for JIRA objects (Issue, Project, etc.)
├── exceptions.py              # Custom exceptions (JiraAPIError, JiraClientError, etc.)
├── messages.py                # Centralized user-facing strings
├── plugin.py                  # The JiraPlugin definition
├── steps/                     # Workflow steps
│   ├── search_saved_query_step.py
│   ├── prompt_select_issue_step.py
│   ├── get_issue_step.py
│   ├── ai_analyze_issue_step.py
│   └── list_projects_step.py
├── utils/                     # Utilities
│   ├── issue_sorter.py        # Issue sorting logic
│   └── saved_queries.py       # Predefined JQL queries
└── workflows/                 # YAML workflow definitions
    └── analyze-my-issues.yaml
```

---

## 🤖 Core Components

### `JiraClient` (`clients/jira_client.py`)

This is the main entry point for all JIRA operations. It uses `requests` to interact with the JIRA REST API and parses responses into structured Python objects defined in `models.py`.

**Authentication:**
- Uses **Bearer token** authentication for JIRA Server/Data Center
- Personal Access Tokens (PAT) are stored securely in the system keychain

**Key Methods:**
- `search_issues(jql: str, max_results: int) -> List[JiraTicket]`: Search issues using JQL
- `get_issue(issue_key: str) -> JiraTicket`: Get full details of a specific issue
- `get_all_projects() -> List[Dict]`: List all accessible JIRA projects
- `_make_request(method: str, endpoint: str, **kwargs) -> Union[Dict, List]`: Generic API request handler

**Features:**
- Automatic error handling with custom exceptions
- None-safe field access for missing JIRA fields
- Configurable timeout and caching (cache currently disabled)

### `JiraPlugin` (`plugin.py`)

This class is the entry point for the plugin system. It is responsible for:
- Declaring the plugin's `name` ("jira")
- Initializing the `JiraClient` with configuration from `.titan/config.toml`
- Retrieving the API token from system keychain (multi-project support)
- Providing the `JiraClient` instance to the `WorkflowContextBuilder`
- Exposing workflow steps via the `get_steps()` method
- Providing the workflows directory path via the `workflows_path` property

**Configuration Model** (`core/plugins/models.py`):
```python
class JiraPluginConfig(BaseModel):
    base_url: str          # JIRA instance URL (e.g., "https://jiranext.masorange.es")
    email: str             # User email for authentication
    api_token: Optional[str]  # Personal Access Token (stored in keychain, not config)
    default_project: str   # Default project key (e.g., "ECAPP")
    timeout: int = 30      # Request timeout in seconds
    enable_cache: bool = True
    cache_ttl: int = 300
```

**Secret Management:**
- API tokens are stored in system keychain with project-specific keys
- Format: `{project_name}_jira_api_token` (e.g., `titan-cli_jira_api_token`)
- Supports fallback to environment variables for backwards compatibility

### Workflow Steps (`steps/`)

Each file in this directory defines one or more `StepFunction`s.

#### 1. `search_saved_query_step.py`

Searches JIRA issues using predefined JQL queries from `utils/saved_queries.py`.

```python
def search_saved_query_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Search JIRA using a saved query.

    Inputs (from ctx.data):
        query_name (str): Name of the saved query to use
        project (str, optional): Project key (uses default_project if not provided)
        max_results (int, optional): Maximum results to return (default: 50)

    Outputs (saved to ctx.data):
        jira_issues (list): List of JiraTicket objects
        jira_issue_count (int): Number of issues found
    """
```

**Features:**
- Displays results in a sortable table (Status → Priority → Key)
- Supports parameter substitution in JQL queries (`{project}`)
- Customizable max results

#### 2. `prompt_select_issue_step.py`

Interactive issue selection from search results.

```python
def prompt_select_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prompts user to select an issue from search results.

    Inputs (from ctx.data):
        jira_issues (list): List of JiraTicket objects

    Outputs (saved to ctx.data):
        jira_issue_key (str): Selected issue key (e.g., "ECAPP-12282")
        selected_issue (JiraTicket): The selected issue object
    """
```

**Features:**
- Numeric selection (1-based index)
- Displays issue summary for easy selection
- Validates user input

#### 3. `get_issue_step.py`

Fetches full details for a specific JIRA issue.

```python
def get_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Get full details of a JIRA issue.

    Inputs (from ctx.data):
        jira_issue_key (str): Issue key to fetch

    Outputs (saved to ctx.data):
        jira_issue (JiraTicket): Full issue details
    """
```

**Features:**
- Fetches all issue fields (description, labels, components, etc.)
- Displays issue summary with key metadata

#### 4. `ai_analyze_issue_requirements`

AI-powered analysis of issue requirements.

```python
def ai_analyze_issue_requirements(ctx: WorkflowContext) -> WorkflowResult:
    """
    Analyze JIRA issue requirements using AI.

    Inputs (from ctx.data):
        jira_issue (JiraTicket): Issue to analyze

    Outputs (saved to ctx.data):
        ai_analysis (str): AI-generated analysis
        analyzed_issue_key (str): Key of analyzed issue
    """
```

**Features:**
- Comprehensive AI analysis with 7 sections:
  1. Issue Overview
  2. Requirements Breakdown
  3. Technical Considerations
  4. Potential Challenges
  5. Implementation Approach
  6. Missing Information
  7. Estimated Complexity
- Displays analysis as formatted markdown
- Requires AI provider to be configured

#### 5. `list_projects_step.py`

Lists all JIRA projects accessible to the user.

```python
def list_projects_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    List all JIRA projects the user has access to.

    Outputs (saved to ctx.data):
        jira_projects (list): List of project dicts
        jira_project_count (int): Number of projects found
    """
```

**Features:**
- Displays projects in formatted table
- Shows project key, name, and type
- Useful for discovering correct project keys

### Workflows (`workflows/`)

#### `analyze-my-issues.yaml`

Complete workflow for analyzing JIRA issues with AI.

```yaml
name: "Analyze JIRA Issues"
description: "List all open issues ready for development and analyze selected issue with AI"

params:
  query_name: "open_issues"  # Can override

steps:
  - search_open_issues       # Search using saved query
  - prompt_select_issue      # Interactive selection
  - get_issue_details        # Fetch full details
  - ai_analyze_issue         # AI analysis
```

**Flow:**
1. Searches issues (default: "Open" or "Ready to Dev")
2. Displays sorted table
3. Prompts for selection
4. Fetches full issue details
5. Performs AI-powered requirements analysis

### Utilities (`utils/`)

#### `IssueSorter` (`utils/issue_sorter.py`)

Encapsulated sorting logic for JIRA issues.

```python
class IssueSorter:
    """
    Sorts JIRA issues by Status → Priority → Key.

    Features:
    - Configurable status and priority order
    - Case-insensitive matching
    - Handles unknown values gracefully
    - Fully tested with 100% coverage
    """
```

**Usage:**
```python
sorter = IssueSorter()
sorted_issues = sorter.sort_issues(issues)
```

#### `SavedQueries` (`utils/saved_queries.py`)

Registry of predefined JQL queries.

**Available Queries:**
- `open_issues` - Open or Ready to Dev issues
- `my_open_issues` - My open issues
- `my_issues` - All my issues
- `my_bugs` - My open bugs
- `current_sprint` - Issues in current sprint
- `team_open` - All open team issues
- And 15+ more...

**Usage:**
```python
jql = SavedQueries.format('current_sprint', project='ECAPP')
# Result: "sprint in openSprints() AND project = ECAPP"
```

---

## 🔧 Configuration

### Interactive Configuration

```bash
titan plugins install jira
# Then configure when prompted
```

### Manual Configuration

**Project Config** (`.titan/config.toml`):
```toml
[plugins.jira]
enabled = true

[plugins.jira.config]
base_url = "https://jiranext.masorange.es"
email = "your.email@company.com"
default_project = "ECAPP"
timeout = 30
enable_cache = true
cache_ttl = 300
```

**API Token** (System Keychain):
- Stored with key: `{project_name}_jira_api_token`
- Generated from JIRA profile → Personal Access Tokens
- Never stored in config files

---

## 🧪 Testing

Tests for this plugin are located in the `tests/` directory.

**Test Structure:**
```
tests/
├── utils/
│   └── test_issue_sorter.py    # IssueSorter tests (16 tests, 100% coverage)
└── (future test files)
```

**Running Tests:**
```bash
cd plugins/titan-plugin-jira
poetry run pytest
poetry run pytest --cov=titan_plugin_jira
```

**Testing Steps:**
Use `pytest` and `unittest.mock` to mock the `JiraClient` when testing steps in isolation.

---

## 🔐 Security

- **Never commit API tokens** to version control
- Tokens are stored in **system keychain** (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- Project-specific tokens support multiple projects
- Fallback to environment variables for CI/CD environments

---

## 📚 Additional Notes

### JIRA Server vs JIRA Cloud

This plugin is designed for **JIRA Server/Data Center** with **Bearer token authentication** using Personal Access Tokens.

For JIRA Cloud, you would need:
- Basic Auth with `email:api_token` in base64
- API token from Atlassian Account settings (not JIRA profile)

### Extending the Plugin

**Adding a New Step:**
1. Create step file in `steps/`
2. Register in `plugin.py` → `get_steps()`
3. Add to appropriate workflow YAML

**Adding a New Query:**
1. Add to `utils/saved_queries.py` → `SavedQueries` class
2. Use in workflows with `query_name` parameter

**Adding a New Workflow:**
1. Create YAML file in `workflows/`
2. Workflow is automatically discovered via `workflows_path`

---

**Last Updated**: 2025-12-12
**Maintainers**: @finxeto, @raulpedrazaleon
