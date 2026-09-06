# AGENTS.md

Documentation for AI coding agents working on Titan CLI.

---

## 🧭 Session Bootstrap

Before doing any work in this repo, read [`harness/README.md`](harness/README.md) — it names
the current-focus domain/task and points to that domain's own state files
(`feature-list.json`, `progress.md`, `session-handoff.md`). Don't ask which task we're on;
that file answers it.

---

## 📋 Project Overview

**Titan CLI** is a modular development tools orchestrator that streamlines workflows through plugins, configuration management, and an intuitive terminal UI.

**Tech Stack:**
- **CLI Framework:** Typer
- **Terminal UI:** Rich
- **Data Validation:** Pydantic
- **Package Manager:** Poetry
- **Testing:** pytest
- **Plugin System:** Python entry points

**Core Capabilities:**
- Centralized project configuration (`.titan/config.toml`)
- Plugin-based extensibility (GitHub, Git, Jira, AI)
- Rich terminal UI with theme-aware components
- Workflow engine for composing atomic steps
- Optional AI integration for code reviews and automation

**Architecture Layers:**
1. **Core:** Configuration, plugin discovery, project scanning
2. **Commands:** CLI command implementations
3. **UI:** Theme-aware components and composite views
4. **Engine:** Workflow orchestration (future)
5. **AI:** Multi-provider AI integration (future)

For high-level architecture overview, see [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Agent Skills

Project-maintained agent skills now live in `.claude/skills/`.

- Use `.claude/skills/titan-official-plugin-workflow-builder/` for workflows that belong to official plugins inside this repository.

Shared workflow-authoring skills are maintained outside this repository. In `titan-cli`, keep only the official-plugin skill here.

---

## 🚀 Quick Start

### Setup
```bash
# Clone and install
git clone <repo>
cd titan-cli
poetry install

# Install with development dependencies
poetry install --with dev,ai-all

# Alternative: pipx for isolated install
pipx install -e .
```

### Development Commands
```bash
# Run CLI locally
poetry run titan

# Run tests
poetry run pytest

# Run specific test file
poetry run pytest tests/ui/components/test_typography.py

# Preview UI components
poetry run titan preview panel
poetry run titan preview typography
poetry run titan preview menu

# Check plugin status
poetry run titan plugins list
poetry run titan plugins doctor
poetry run titan plugins info git
poetry run titan plugins configure git

# Linting and formatting
poetry run ruff check titan_cli/
poetry run black titan_cli/
```

---

## ✨ Interactive Mode

When `titan` is run without any subcommands, it enters an interactive mode designed to guide the user.

### First-Time Setup

If no global `project_root` is configured (`~/.titan/config.toml`), the CLI will prompt the user to set it. This is the root directory where Titan will look for your projects.

### Main Menu

Once the setup is complete, a main menu is displayed, which loops after each action. It provides the following options:

- **List Configured Projects:** Scans the `project_root` and lists all projects that have a `.titan/config.toml` file, as well as other Git repositories that are candidates for initialization.
- **Configure a New Project:**
  1.  Displays a sub-menu listing all unconfigured Git repositories.
  2.  After selecting a project, it starts an interactive prompt to define the project `name` and `type`.
  3.  Creates a `.titan/config.toml` file in the project's root directory.
- **Exit:** Exits the interactive session.

---

## 📁 Project Structure

```
titan_cli/
├── core/               # Core logic (config, plugins, discovery)
├── commands/           # CLI commands (init, projects, etc.)
├── ui/
│   ├── components/     # Atomic UI wrappers (Panel, Typography, Table, Spacer)
│   └── views/          # Composite UI (Banner, Prompts, Menus)
├── engine/             # Workflow engine (future)
└── ai/                 # AI integration (future)
```

**Key files:**
- `cli.py` - Main Typer app
- `messages.py` - Centralized user-facing strings
- `ui/theme.py` - Centralized theming (TITAN_THEME)
- `ui/console.py` - Singleton Rich Console

---

## 🎨 UI Architecture

### Components vs Views

**Components** (`ui/components/`):
- Pure wrappers around Rich library
- DO NOT compose other project components
- Examples: `PanelRenderer`, `TextRenderer`, `TableRenderer`, `SpacerRenderer`

**Views** (`ui/views/`):
- Composite components that USE other components
- Can have business logic
- Examples: `PromptsRenderer` (uses TextRenderer), `MenuRenderer` (uses TextRenderer + Spacer)

### Creating a New Component

1. **File location:**
   - Pure component → `ui/components/my_component.py`
   - Composite view → `ui/views/my_view.py`

2. **Component structure:**
```python
# ui/components/my_component.py
from typing import Optional
from rich.console import Console
from ..console import get_console

class MyComponentRenderer:
    """Description of component"""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or get_console()  # Theme-aware console

    def render(self, data):
        # Use theme styles: "success", "error", "info", "warning", "primary"
        self.console.print("[success]Success message[/success]")
```

3. **Create preview:**
```python
# ui/components/__previews__/my_component_preview.py
from titan_cli.ui.components.my_component import MyComponentRenderer

def preview_all():
    renderer = MyComponentRenderer()
    renderer.render("test data")

if __name__ == "__main__":
    preview_all()
```

4. **Add preview command:**
```python
# preview.py
@preview_app.command("my_component")
def preview_my_component():
    """Shows preview of MyComponent."""
    runpy.run_module("titan_cli.ui.components.__previews__.my_component_preview", run_name="__main__")
```

5. **Test it:**
```bash
poetry run titan preview my_component
```

---

## 🎨 Theming & Styling

### Theme Configuration (`ui/theme.py`)

All colors and styles are centralized in `TITAN_THEME`:

```python
TITAN_THEME = Theme({
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold cyan",
    "primary": "bold blue",
    "dim": "dim",
})
```

### Using Styles

**Single-style text:**
```python
text = TextRenderer()
text.success("Operation completed!")  # Uses "success" style
text.error("Something failed!")       # Uses "error" style
text.body("Normal text", style="dim") # Custom style
```

**Multi-style text (inline):**
```python
text.styled_text(
    ("  1. ", "primary"),      # Number in primary color
    ("Item label", "bold"),    # Label in bold
    (" - ", "dim"),            # Separator dimmed
    ("description", "dim")     # Description dimmed
)
```

**Console direct (when needed in Views):**
```python
from rich.text import Text

# Multi-styled line (allowed in Views for complex cases)
line = Text()
line.append("Number: ", style="primary")
line.append("Value", style="bold")
self.console.print(line)
```

---

## 📝 Messages & i18n

**All user-facing strings go in `messages.py`:**

For the core `titan_cli`, messages are located in `titan_cli/messages.py`.
**Plugins must maintain their own `messages.py` file** within their respective plugin directory (e.g., `plugins/my-plugin/my_plugin/messages.py`) to centralize their user-facing strings.

```python
# messages.py
class Messages:
    class UI:
        LOADING = "⏳ Loading..."
        DONE = "✅ Done"

    class Prompts:
        INVALID_INPUT = "❌ Invalid input. Please try again."

msg = Messages()

# Usage
from titan_cli.messages import msg
text.error(msg.Prompts.INVALID_INPUT)
```

**Why:**
- Centralized maintenance
- Easy to find all strings
- Future i18n support
- Consistency across app

---

## 🧪 Testing

### Test Structure

```
tests/
├── commands/           # CLI command tests
├── core/               # Core logic tests
└── ui/
    ├── components/     # Component tests
    └── views/          # View tests
```

### Testing Components

Use fixtures and mocks for isolation:

```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_console():
    return MagicMock()

def test_my_component(mock_console):
    from titan_cli.ui.components.my_component import MyComponentRenderer

    renderer = MyComponentRenderer(console=mock_console)
    renderer.render("test")

    # Assert console.print was called
    assert mock_console.print.called
```

### Running Tests

```bash
# All tests
poetry run pytest

# With coverage
poetry run pytest --cov=titan_cli

# Specific test
poetry run pytest tests/ui/components/test_typography.py::test_styled_text

# Watch mode (useful during development)
poetry run pytest-watch
```

---

## 🔧 Configuration System

### Config Files

```
~/.titan/config.toml              # Global config (AI keys, project root)
/project/.titan/config.toml       # Project config (plugins, workflows)
```

### Config Structure (TOML)

```toml
# Global config (~/.titan/config.toml)
[core]
project_root = "/home/user/projects"

[ai]
provider = "anthropic"
model = "claude-sonnet-4"

# Global plugin configuration
[plugins.git]
enabled = true
config.main_branch = "develop" # All projects will use 'develop' by default
config.default_remote = "origin"

# Project config (.titan/config.toml)
[project]
name = "my-app"
type = "fullstack"

# Project-specific plugin overrides
[plugins.git]
config.main_branch = "main" # This specific project uses 'main'
```

### Config Models (Pydantic)

All config is validated using Pydantic models. Core models are in `core/models.py`. Plugin-specific configuration models are in `core/plugins/models.py`.

```python
# titan_cli/core/plugins/models.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List

class PluginConfig(BaseModel):
    enabled: bool = Field(True, description="Whether the plugin is enabled.")
    config: Dict[str, Any] = Field(default_factory=dict, description="Plugin-specific configuration options.")

class GitPluginConfig(BaseModel):
    main_branch: str = Field("main", description="Main/default branch name")
    default_remote: str = Field("origin", description="Default remote name")

class GitHubPluginConfig(BaseModel):
    """Configuration for GitHub plugin."""
    repo_owner: Optional[str] = Field(None, description="GitHub repository owner (user or organization). Auto-detected if not provided.")
    repo_name: Optional[str] = Field(None, description="GitHub repository name. Auto-detected if not provided.")
    default_branch: Optional[str] = Field(None, description="Default branch to use (e.g., 'main', 'develop').")
    pr_template_path: Optional[str] = Field(None, description="Path to PR template file within the repository.")
    auto_assign_prs: bool = Field(False, description="Automatically assign PRs to the author.")
    require_linear_history: bool = Field(False, description="Require linear history for PRs.")

# titan_cli/core/models.py
from pydantic import BaseModel, Field
from .plugins.models import PluginConfig # Import from new location

class TitanConfigModel(BaseModel):
    project: Optional[ProjectConfig] = None
    ai: Optional[AIConfig] = None
    plugins: Dict[str, PluginConfig] = Field(default_factory=dict)
```

### SecretManager (`core/secrets.py`)

The `SecretManager` provides a unified interface for securely managing sensitive information across different scopes. It implements a 3-level cascading priority system for retrieving secrets:

1.  **Environment Variables (`env` scope):** Highest priority. Secrets set in environment variables (e.g., `GITHUB_TOKEN`) are checked first. Project-specific secrets loaded from `.titan/secrets.env` are also made available here.
2.  **Project Secrets (`project` scope):** Stored in a `.titan/secrets.env` file within the project directory. These are typically shared among team members working on the same project. They are loaded into environment variables upon initialization of the `SecretManager`.
3.  **User Keyring (`user` scope):** Lowest priority. Secrets are stored securely in the operating system's keyring (e.g., macOS Keychain, Linux Keyring, Windows Credential Manager). These are personal credentials.

This cascade ensures flexibility, allowing environment variables to override project-specific or personal settings for CI/CD environments, while still providing secure storage options for local development.

**Usage:**

```python
from titan_cli.core.secrets import SecretManager

# Initialize with current working directory or a specific project path
secrets = SecretManager() 

# Get a secret (cascading priority)
api_key = secrets.get("ANTHROPIC_API_KEY")

# Set a secret (user scope by default)
secrets.set("GITHUB_TOKEN", "ghp_...", scope="user")

# Set a project-specific secret
secrets.set("DB_PASSWORD", "super_secret", scope="project")

# Interactively prompt for a secret
if not secrets.get("GEMINI_API_KEY"):
    secrets.prompt_and_set("GEMINI_API_KEY", "Enter your Gemini API Key")
```

### Using Config

```python
from titan_cli.core.config import TitanConfig

config = TitanConfig()  # Loads and merges global + project
print(config.config.project.name)
print(config.config.ai.default_connection)  # Default AI connection ID
print(config.config.ai.connections)  # Dict of all configured AI connections

# Check enabled plugins
if config.is_plugin_enabled("github"):
    # ... use github plugin
```

---

## 🔌 Plugin System

Titan CLI features a modular plugin system that allows its functionality to be extended with new clients, workflow steps, and commands.

### Plugin Documentation Maintenance

When working on an official plugin, you must keep its public plugin documentation in sync with the code.

This applies when you:

- Add a new public client function
- Remove a public client function
- Change parameters of an existing public client function
- Change the expected usage or behavior of an existing public client function
- Add a workflow that exposes a new user-facing plugin capability

Public workflow steps exposed through `plugin.py -> get_steps()` are part of that contract.

This also applies when you:

- Add a new public workflow step
- Remove a public workflow step
- Rename a public workflow step
- Change the required `ctx.data` inputs of a public workflow step
- Change the metadata outputs or return behavior (`Success`, `Skip`, `Exit`, `Error`) of a public workflow step

Update the matching page in the `Plugins` documentation section:

- `docs/plugins/git/overview.md`
- `docs/plugins/git/client-api.md`
- `docs/plugins/git/workflow-steps.md`
- `docs/plugins/git/built-in-workflows.md`
- `docs/plugins/github/overview.md`
- `docs/plugins/github/client-api.md`
- `docs/plugins/github/workflow-steps.md`
- `docs/plugins/github/built-in-workflows.md`
- `docs/plugins/jira/overview.md`
- `docs/plugins/jira/client-api.md`
- `docs/plugins/jira/workflow-steps.md`
- `docs/plugins/jira/built-in-workflows.md`
- `docs/plugins/_meta/*.json`
- `docs/plugins/_generated/*.json`

At minimum, the documentation must show:

- What the operation does
- How it is called
- Which parameters are required
- Which parameters are optional
- Any important usage constraints

For public workflow steps, docstrings must use the exact canonical section headers:

- `Requires:`
- `Inputs (from ctx.data):`
- `Outputs (saved to ctx.data):`
- `Returns:`

`Returns:` is always required for public steps exposed through `get_steps()`.

When you change public steps in this repository, run the project workflows:

- `sync-plugin-docs`
- `validate-plugin-docs`

### Core Concepts

- **Discovery**: Plugins are packaged as separate Python packages and discovered at runtime using `importlib.metadata` to look for the `titan.plugins` entry point group.
- **Base Class**: Every plugin must inherit from the `TitanPlugin` abstract base class (`titan_cli/core/plugins/plugin_base.py`), which defines the contract for all plugins.
- **Dependency Resolution**: The `PluginRegistry` automatically resolves dependencies between plugins. A plugin can declare its dependencies by overriding the `dependencies` property. The registry ensures that dependencies are initialized before the plugins that need them.
- **Error Handling**: Plugins should not handle their own initialization errors with `try...except` blocks. Instead, they should raise specific exceptions (e.g., `MyClientError`). The `PluginRegistry` will catch these exceptions, disable the failing plugin, and report the error to the user through the CLI.

### Installing Plugins

Plugins are installed into `titan-cli`'s isolated environment using `pipx inject`.

```bash
# First, install the core CLI if you haven't
pipx install . -e

# Then, inject plugins
pipx inject titan-cli titan-plugin-git
pipx inject titan-cli titan-plugin-github
```
For local development where plugins are in subdirectories, add them to the main `pyproject.toml` as a path dependency.

### Plugin Anatomy

A plugin is a standard Python package that typically follows this structure. For a concrete example, refer to `plugins/titan-plugin-git/`:

```
plugins/my-cool-plugin/
├── pyproject.toml             # Defines the plugin and its entry point
├── my_cool_plugin/
│   ├── __init__.py
│   ├── plugin.py              # Contains the main TitanPlugin class
│   ├── clients/               # Wrappers for external APIs or CLIs
│   ├── operations/            # Pure business logic (NEW - see Operations Pattern)
│   ├── models.py              # Data models for plugin-specific entities
│   ├── exceptions.py          # Custom exceptions for the plugin
│   ├── messages.py            # **Centralized user-facing strings for the plugin**
│   └── steps/                 # Workflow steps provided by the plugin
└── tests/
    └── operations/            # Unit tests for operations (NEW)
```

#### `pyproject.toml`

The plugin must declare itself in the `[project.entry-points."titan.plugins"]` section.

```toml
# plugins/my-cool-plugin/pyproject.toml
[project.entry-points."titan.plugins"]
my-plugin-name = "my_cool_plugin.plugin:MyCoolPlugin"
```

#### `plugin.py`

This file defines the main plugin class that inherits from `TitanPlugin`. It acts as the entry point for the plugin, responsible for its initialization and exposing its capabilities.

```python
from titan_cli.core import TitanPlugin
# Import plugin-specific client, models, and messages
from .clients.my_client import MyClient
from .messages import msg

class MyCoolPlugin(TitanPlugin):
    @property
    def name(self) -> str:
        # The unique name of the plugin (e.g., "git", "github")
        return "my-plugin-name"

    @property
    def dependencies(self) -> list[str]:
        # Declare any other Titan plugins this plugin depends on.
        # Example: if this plugin uses Git operations, it might depend on "git".
        return ["git"] # Example dependency

    def initialize(self, config: 'TitanConfig', secrets: 'SecretManager'):
        """
        Initialize the plugin with its specific configuration.
        """
        # Extract and validate the plugin's configuration
        plugin_config_data = config.config.plugins.get(self.name, {}).config
        validated_config = GitPluginConfig(**plugin_config_data)

        # Initialize the client with the validated configuration
        self.client = MyClient(
            main_branch=validated_config.main_branch,
            default_remote=validated_config.default_remote
        )

    def get_client(self) -> MyClient:
        if not hasattr(self, 'client') or self.client is None:
            raise MyClientError("Plugin not initialized. The client is not available.")
        return self.client

    def get_config_schema(self) -> dict:
        """Returns the JSON schema for the plugin's configuration."""
        return GitPluginConfig.model_json_schema()
    
    def get_steps(self) -> dict:
        # Expose workflow steps provided by this plugin.
        # Steps are typically functions in the 'steps/' directory.
        from .steps import step_one, step_two
        return {
            "step_one": step_one,
            "step_two": step_two,
        }
```

#### Other Key Directories/Files:

-   **`clients/`**: Contains Python classes that wrap external APIs, CLI tools (like `GitClient` for `git`), or internal services. These clients should encapsulate the logic for interacting with external systems.
-   **`models.py`**: Defines Pydantic models for data structures specific to the plugin (e.g., `GitStatus`, `GitBranch` in `titan-plugin-git`).
-   **`exceptions.py`**: Custom exceptions specific to the plugin's operations.
-   **`messages.py`**: As highlighted in the "Messages & i18n" section, this file centralizes all user-facing strings for the plugin, making them easy to manage and prepare for internationalization.
-   **`steps/`**: Contains individual `StepFunction` implementations that can be used within the Workflow Engine. These steps should be atomic and focused on a single logical operation (e.g., `status_step.py`, `commit_step.py` in `titan-plugin-git`).

---

## 🤖 AI Integration

Titan CLI includes a modular AI integration layer that supports multiple AI connections.
Connections can be either direct providers (Anthropic, OpenAI, Gemini) or LLM gateways
that expose OpenAI-compatible endpoints such as LiteLLM.

### File Structure (`ai/`)

The `ai` layer is organized as follows:

```
titan_cli/ai/
├── __init__.py
├── client.py               # AIClient facade
├── constants.py            # Default models and provider metadata
├── exceptions.py           # Custom AI-related exceptions
├── models.py               # Data models (AIRequest, AIResponse)
├── oauth_helper.py         # Helper for Google Cloud OAuth
├── litellm_client.py       # Shared OpenAI-compatible gateway client
└── providers/
    ├── __init__.py
    ├── base.py             # AIProvider abstract base class
    ├── anthropic.py
    ├── gemini.py
    ├── openai.py
    └── litellm.py
```

### Core Components

-   **`AIClient` (`ai/client.py`):** Main facade for AI usage. It reads the configured AI connection, retrieves secrets via `SecretManager`, and instantiates the correct direct provider or gateway adapter. Use `connection_id` to select a specific connection.
-   **`AIProvider` (`ai/providers/base.py`):** Abstract base class implemented by direct providers and the LiteLLM/OpenAI-compatible gateway provider.
-   **`LiteLLMClient` (`ai/litellm_client.py`):** Shared client for OpenAI-compatible gateways used for connection testing and model discovery.

### Configuration

AI configuration supports **multiple connections** simultaneously.
Each connection can be:
- **LLM Gateway**: one endpoint exposing multiple models through an OpenAI-compatible API
- **Direct Provider**: a direct vendor integration such as Anthropic, OpenAI, or Gemini

AI connections are configured from the TUI:
- Main menu option: `AI Configuration`
- Then create a new connection and optionally set it as default

The configuration workflow:
1.  Select connection type (`LLM Gateway` or `Direct Provider`)
2.  For gateways, enter the base URL
3.  Select the direct provider source when applicable
4.  Provide API key (stored securely via `SecretManager`)
5.  Select or enter the default model
6.  Assign a friendly name to the connection
7.  Optionally configure advanced settings (temperature, max_tokens)
8.  Optionally mark as default connection
9.  Test the connection

Configuration is stored in the global `~/.titan/config.toml` file:

```toml
[ai]
default_connection = "work-gateway"

[ai.connections.work-gateway]
name = "Work Gateway"
kind = "gateway"
gateway_type = "openai_compatible"
base_url = "https://llm.company.com"
default_model = "gemini-2.5-pro"
temperature = 0.7
max_tokens = 4096

[ai.connections.personal-claude]
name = "Personal Claude"
kind = "direct_provider"
provider = "anthropic"
default_model = "claude-sonnet-4-5"
temperature = 0.7
max_tokens = 4096
```

Titan still loads legacy AI config and migrates it to this structure automatically.

### Usage

To use the AI client in a command or other part of the application:

```python
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ai.client import AIClient
from titan_cli.ai.models import AIMessage
from titan_cli.ai.exceptions import AIConfigurationError

# 1. Initialize config and secrets
config = TitanConfig()
secrets = SecretManager()

# 2. Check if AI is configured
if not config.config.ai or not config.config.ai.connections:
    print("No AI connections configured.")
    return

# 3. Create the AI client (uses default connection)
try:
    ai_client = AIClient(config.config.ai, secrets)
    # Or specify a specific connection:
    # ai_client = AIClient(config.config.ai, secrets, connection_id="work-gateway")
except AIConfigurationError as e:
    print(f"AI not available: {e}")
    return

# 4. Make a request
if ai_client.is_available():
    messages = [AIMessage(role="user", content="Explain the meaning of life.")]

    # Simple request (uses provider's configured settings)
    response = ai_client.generate(messages)
    print(response.content)

    # Request with overrides
    creative_response = ai_client.generate(
        messages,
        temperature=1.2,
        max_tokens=1024
    )
    print(creative_response.content)

# 5. Using specific connections
gateway_client = AIClient(config.config.ai, secrets, connection_id="work-gateway")
personal_client = AIClient(config.config.ai, secrets, connection_id="personal-claude")

# Each client uses its own connection configuration
corp_response = gateway_client.generate(messages)
personal_response = personal_client.generate(messages)
```

---

## ⚡ External CLI Integration

Titan CLI provides a generic system for launching external command-line tools like `claude` or `gemini`. This is managed through a centralized registry that makes adding new CLIs easy and maintainable.

### Core Components

- **`CLILauncher` (`utils/cli_launcher.py`):** A generic class that handles checking for a CLI's availability (`is_available()`) and launching it with the correct arguments. It can handle CLIs that take prompts as positional arguments or via a specific flag (e.g., `-i`).

- **`CLI_REGISTRY` (`utils/cli_configs.py`):** A centralized dictionary that stores the configuration for all supported external CLIs. This is the single source of truth for CLI configurations.

### How to Add a New CLI

To add support for a new external CLI, follow these two steps:

**1. Update the CLI Registry**

Open `titan_cli/utils/cli_configs.py` and add a new entry to the `CLI_REGISTRY` dictionary.

The key for the new entry should be the command-line name of the tool (e.g., `"my-cool-cli"`). The value is a dictionary with the following keys:

- `display_name` (str): The user-friendly name that will be shown in menus.
- `install_instructions` (Optional[str]): A message explaining how to install the tool. If `None`, a generic message will be used.
- `prompt_flag` (Optional[str]): The flag used to pass an initial prompt while keeping the session interactive. If the tool takes the prompt as a positional argument, set this to `None`.

**Example:**

```python
# titan_cli/utils/cli_configs.py

CLI_REGISTRY = {
    "claude": {
        "display_name": "Claude CLI",
        "install_instructions": "Install: npm install -g @anthropic/claude-code",
        "prompt_flag": None  # Uses positional argument
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "install_instructions": None, # No specific instruction
        "prompt_flag": "-i"    # Uses -i flag for prompts
    },
    # Add your new CLI here
    "my-cool-cli": {
        "display_name": "My Cool CLI",
        "install_instructions": "pip install my-cool-cli",
        "prompt_flag": "--prompt"
    }
}
```

**2. Update Menus (If applicable)**

The system is designed to be automatic. Once you add a CLI to the registry, it will automatically appear in two places:

- **The main interactive menu:** The "Launch External CLI" submenu dynamically shows all available CLIs from the registry.
- **AI Configuration:** the CLI becomes selectable as the interactive CLI, which is what `ai_code_assistant` launches. The step never asks mid-run and takes no CLI parameter: it resolves the route through `ctx.ai_router.resolve()`.

If you want to add a direct top-level command for your new CLI (like `titan my-cool-cli`), you can add it to `titan_cli/commands/cli.py`:

```python
# titan_cli/commands/cli.py

# ... (imports)

@cli_app.command("my-cool-cli")
def launch_my_cool_cli(
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for My Cool CLI.")
):
    """
    Launch My Cool CLI.
    """
    launch_cli_tool("my-cool-cli", prompt)
```

That's it! By centralizing the configuration, the rest of the system adapts automatically.

---

## 📋 Code Style & Conventions

### Python Style
- **Black** for formatting (line length: 88)
- **Ruff** for linting
- **Type hints** required for all function signatures
- **Docstrings** for all public classes and methods (Google style)

### Naming Conventions
- **snake_case** for files, functions, variables
- **PascalCase** for classes
- **UPPER_CASE** for constants

### Import Order
```python
# 1. Standard library
from typing import Optional
from pathlib import Path

# 2. Third-party
from rich.console import Console
from pydantic import BaseModel

# 3. Local
from titan_cli.ui.console import get_console
from titan_cli.messages import msg
```

### Dependency Injection
All renderers/components accept optional dependencies:

```python
class MyRenderer:
    def __init__(
        self,
        console: Optional[Console] = None,
        text_renderer: Optional[TextRenderer] = None
    ):
        self.console = console or get_console()
        self.text = text_renderer or TextRenderer(console=self.console)
```

**Why:** Enables testing with mocks

---

## 🚫 Common Mistakes to Avoid

### ❌ DON'T: Use print() or console directly in components
```python
# Bad
print("Success!")
console = Console()
console.print("[green]Success![/green]")
```

### ✅ DO: Use TextRenderer
```python
# Good
text = TextRenderer()
text.success("Success!")
```

### ❌ DON'T: Hardcode colors or styles
```python
# Bad
console.print("[bold green]Success![/bold green]")
```

### ✅ DO: Use theme styles
```python
# Good
console.print("[success]Success![/success]")  # "success" defined in theme
```

### ❌ DON'T: Hardcode user-facing strings
```python
# Bad
text.error("Invalid input. Try again.")
```

### ✅ DO: Use messages.py
```python
# Good
from titan_cli.messages import msg
text.error(msg.Prompts.INVALID_INPUT)
```

### ❌ DON'T: Put pure wrappers in views/
```python
# Bad - PanelRenderer is pure wrapper, should be in components/
titan_cli/ui/views/panel.py
```

### ✅ DO: Follow component/view separation
```python
# Good
titan_cli/ui/components/panel.py      # Pure wrapper (no composition)
titan_cli/ui/views/prompts.py         # Composite (uses TextRenderer + MenuRenderer)
```

### ❌ DON'T: Compose other components in components/
```python
# Bad - TextRenderer in components/ shouldn't use PanelRenderer
class TextRenderer:
    def __init__(self, panel_renderer: PanelRenderer):  # ❌ NO!
        self.panel = panel_renderer
```

### ✅ DO: Keep components pure
```python
# Good - Components only wrap Rich
class TextRenderer:
    def __init__(self, console: Optional[Console] = None):
        self.console = console or get_console()  # ✅ Only Rich/console
```

### ❌ DON'T: Catch exceptions in plugin initialization
```python
# Bad - The plugin hides the error and the CLI doesn't know it failed
def initialize(self, config, secrets):
    try:
        self.client = MyClient()
    except MyClientError as e:
        print(f"Failed to load: {e}") # ❌ Don't print from a plugin
        self.client = None # ❌ Don't swallow the error
```

### ✅ DO: Let exceptions propagate from plugins
```python
# Good - The PluginRegistry will catch, log, and disable the plugin
def initialize(self, config, secrets):
    # Let MyClientError propagate up if it occurs
    self.client = MyClient()
```

---

## 🚀 Workflow System

Titan CLI includes a powerful, declarative workflow system for automating development tasks. Workflows are defined in YAML files and can be discovered from multiple sources with a precedence-based resolution system.

### Architecture Overview

The workflow system follows a similar pattern to the plugin system, with clear separation between **management** (discovery, loading, resolution) and **execution** (running workflows):

```
titan_cli/
├── core/workflows/            # Workflow Management (analogous to PluginRegistry)
│   ├── workflow_registry.py   # Central registry for discovering and managing workflows
│   ├── workflow_sources.py    # Load workflows from multiple sources
│   ├── project_step_source.py # Discover and load project steps (.titan/steps/)
│   ├── workflow_exceptions.py # Workflow-specific exceptions
│   └── models.py              # Workflow data models
│
└── engine/                    # Workflow Execution
    ├── workflow_executor.py   # Executes ParsedWorkflow by running steps
    ├── context.py             # WorkflowContext (dependency injection container)
    ├── builder.py             # WorkflowContextBuilder (fluent API)
    ├── results.py             # WorkflowResult types (Success, Error, Skip)
    ├── steps/
    │   └── command_step.py    # Execute shell commands with venv support
    ├── ui_container.py        # UIComponents container
    └── views_container.py     # UIViews container
```

### Workflow Sources & Precedence

Workflows can be defined in multiple locations with a clear precedence hierarchy:

```
1. Project Workflows     (highest priority)
   .titan/workflows/*.yaml
   ✓ Specific to the project
   ✓ Versioned with the codebase
   ✓ Can override plugin/system workflows

2. User Workflows
   ~/.titan/workflows/*.yaml
   ✓ Personal workflows
   ✓ Not shared with the team

3. System Workflows
   titan_cli/workflows/*.yaml
   ✓ Built-in workflows
   ✓ Shipped with Titan CLI

4. Plugin Workflows      (lowest priority)
   plugins/*/workflows/*.yaml
   ✓ Provided by installed plugins
   ✓ Can be overridden at project level
```

Workflows from higher-priority sources override those from lower-priority sources when they have the same name.

### YAML Workflow Structure

Workflows are defined in YAML with the following structure:

```yaml
# .titan/workflows/create-pr.yaml
name: "Create Pull Request"
description: "Complete workflow for creating a PR with tests and linting"

# Optional: extend another workflow
extends: "plugin:github/create-pr"

# Default parameters (can be overridden)
params:
  base_branch: "develop"
  draft: false

# Hooks for injecting steps (when extending)
hooks:
  before_commit:
    - id: lint
      name: "Run Linter"
      command: "npm run lint"
      on_error: fail

  before_push:
    - id: test
      name: "Run Tests"
      command: "npm test"

  after_pr:
    - id: notify
      name: "Notify Team"
      plugin: slack
      step: send_message
      params:
        channel: "#pull-requests"
        message: "PR created: ${pr_url}"

# Workflow steps
steps:
  - id: git_status
    name: "Check Git Status"
    plugin: git
    step: get_status

  # Hook injection point
  - hook: before_commit

  - id: create_commit
    name: "Create Commit"
    plugin: git
    step: create_commit
    params:
      message: "${commit_message}"  # Variable substitution

  - hook: before_push

  - id: push
    name: "Push to Remote"
    plugin: git
    step: push
    on_error: fail  # Stop workflow if this fails

  - id: create_pr
    name: "Create Pull Request"
    plugin: github
    step: create_pr
    params:
      title: "${pr_title}"
      base: "${base_branch}"
      draft: "${draft}"

  - hook: after_pr
```

### Step Types

#### 1. Plugin Steps

Execute functions provided by plugins. The `requires` key is a list of variables that the `WorkflowExecutor` will validate exist in the context before running the step.

```yaml
- id: create_commit
  name: "Create Commit"
  plugin: git           # Plugin name
  step: create_commit   # Step function from plugin.get_steps()
  requires:
    - commit_message
  on_error: fail        # fail (default) | continue | skip
```

#### 2. Command Steps

Execute shell commands:

```yaml
- id: test
  name: "Run Tests"
  command: "npm test"   # Shell command to execute
  on_error: continue    # Continue even if tests fail
  params:
    use_venv: true      # Optional: activate Poetry virtualenv before running
```

**Advanced Command Step Features:**

- **Variable substitution:** Use `${variable}` syntax in commands
- **Poetry venv activation:** Set `use_venv: true` to run command in Poetry's virtualenv
- **Error handling:** Configure behavior with `on_error: fail|continue|skip`
- **Shell execution mode:** Control command execution security with `use_shell` flag

```yaml
- id: ruff-check
  name: "Run Linter"
  command: "ruff check . --output-format=json"
  params:
    use_venv: true  # Activates poetry env, then runs ruff
  on_error: fail
```

**Security: Shell Execution Mode**

By default, commands are executed **without shell** (`use_shell: false`) for security. The command is split using `shlex.split()` to prevent command injection attacks.

```yaml
# SAFE (default): Command is split, no shell features
- id: safe-echo
  command: "echo ${message}"
  # use_shell defaults to false - uses shlex.split()
```

When you need shell features (pipes, redirects, wildcards), set `use_shell: true`:

```yaml
# REQUIRES SHELL: Uses pipes
- id: grep-logs
  command: "cat app.log | grep ERROR | head -10"
  params:
    use_shell: true  # ⚠️ Required for pipes, but less secure
```

**⚠️ Security Warning:** Only use `use_shell: true` when necessary and **never** with untrusted input from `${variables}` that could contain user data.

**When to use `use_shell`:**

| Feature Needed | `use_shell` | Example |
|----------------|-------------|---------|
| Simple commands | `false` (default) | `pytest tests/` |
| Commands with arguments | `false` (default) | `ruff check . --fix` |
| Variable substitution (trusted) | `false` (default) | `echo ${project_name}` |
| Pipes (`\|`) | `true` ⚠️ | `cat file \| grep pattern` |
| Redirects (`>`, `>>`, `<`) | `true` ⚠️ | `echo "test" > output.txt` |
| Wildcards (`*`, `?`) | `true` ⚠️ | `ls *.py` |
| Command chaining (`&&`, `\|\|`) | `true` ⚠️ | `make && make test` |

**Best Practice:** Prefer simple commands without `use_shell` when possible. If you need shell features, ensure all `${variables}` come from trusted sources (workflow params, not user input).

#### 3. Project Steps

**Execute custom Python functions** defined in `.titan/steps/` directory. This allows projects to define workflow logic without creating a full plugin.

**Convention:**
- File: `.titan/steps/{step_name}.py`
- Function: `def {step_name}(ctx: WorkflowContext) -> WorkflowResult`
- Reference: `plugin: project` in YAML

**Example: Custom linter step**

```python
# .titan/steps/ruff_linter.py
import json
import subprocess
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult


def ruff_linter(ctx: WorkflowContext) -> WorkflowResult:
    """
    Run ruff with autofix and show diff between before/after.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    project_root = ctx.get("project_root", ".")

    # 1. Scan before fix
    ctx.textual.dim_text("Running initial ruff scan...")
    result_before = subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--output-format=json"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    try:
        errors_before = json.loads(result_before.stdout) if result_before.stdout else []
    except json.JSONDecodeError:
        return Error(f"Failed to parse ruff output as JSON.\n{result_before.stdout}")

    # 2. Auto-fix
    ctx.textual.dim_text("Applying auto-fixes...")
    subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--fix", "--quiet"],
        capture_output=True,
        cwd=project_root
    )

    # 3. Scan after fix
    result_after = subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--output-format=json"],
        capture_output=True,
        text=True,
        cwd=project_root
    )
    errors_after = json.loads(result_after.stdout) if result_after.stdout else []

    # 4. Show summary with Textual components
    fixed_count = len(errors_before) - len(errors_after)

    if fixed_count > 0:
        ctx.textual.success_text(f"Auto-fixed {fixed_count} issue(s)")

    if not errors_after:
        ctx.textual.success_text("All linting issues resolved!")
        return Success("Linting passed")

    # 5. Show remaining errors
    ctx.textual.warning_text(f"{len(errors_after)} issue(s) require manual fix:")
    for error in errors_after:
        file_path = error.get("filename", "Unknown")
        location = error.get("location", {})
        row = location.get("row", "?")
        code = error.get("code", "")
        message = error.get("message", "")
        ctx.textual.error_text(f"  {file_path}:{row} - [{code}] {message}")

    return Error(f"{len(errors_after)} linting issues remain")
```

**Usage in workflow:**

```yaml
# .titan/workflows/create-pr-ai.yaml
extends: "plugin:github/create-pr-ai"

hooks:
  before_commit:
    - id: ruff-lint
      name: "Run Ruff Linter"
      plugin: project        # Virtual plugin for project steps
      step: ruff_linter      # Loads .titan/steps/ruff_linter.py
      on_error: fail
```

**When to use Project Steps vs Command Steps:**

| Use Case | Command Step | Project Step |
|----------|-------------|--------------|
| Run linter with default output | ✅ | ❌ |
| Run linter with custom formatting | ❌ | ✅ |
| Execute simple shell command | ✅ | ❌ |
| Compare before/after results | ❌ | ✅ |
| Complex logic with conditionals | ❌ | ✅ |
| Use UIComponents for output | ❌ | ✅ |
| No Python knowledge required | ✅ | ❌ |

### Parameter Substitution

Workflows support dynamic parameter substitution using `${variable}` syntax:

```yaml
steps:
  - id: create_pr
    params:
      title: "${pr_title}"      # From ctx.data (set by previous steps)
      base: "${base_branch}"    # From workflow params
      branch: "${current_branch}" # From context
```

**Resolution priority:**
1. `ctx.data` (highest) - Set dynamically by previous steps
2. `workflow.params` - Defined in the workflow YAML
3. Config values (future) - From `.titan/config.toml`

### Workflow Extension with Hooks

Workflows can extend other workflows and inject steps at specific points using hooks:

**Base workflow (from plugin):**

```yaml
# plugins/titan-plugin-github/workflows/create-pr.yaml
name: "Create Pull Request"

hooks:
  - before_commit  # Hook injection points
  - before_push
  - after_pr

steps:
  - id: status
    plugin: git
    step: get_status

  - hook: before_commit  # Steps can be injected here

  - id: commit
    plugin: git
    step: create_commit
```

**Extended workflow (project-specific):**

```yaml
# .titan/workflows/create-pr.yaml
extends: "plugin:github/create-pr"

hooks:
  before_commit:  # Inject steps at this hook
    - id: lint
      command: "npm run lint"
    - id: format
      command: "npm run prettier"
```

**Result:** The extended workflow executes `lint` and `format` at the `before_commit` hook point.

### Core Components

#### 1. WorkflowRegistry (`core/workflows/workflow_registry.py`)

Central registry for discovering and managing workflows from all sources. Analogous to `PluginRegistry`.

```python
from titan_cli.core.config import TitanConfig

config = TitanConfig()

# List all available workflows
workflows = config.workflows.list_available()

# Get a specific workflow (fully resolved and parsed)
workflow = config.workflows.get_workflow("create-pr")
# Returns ParsedWorkflow with extends resolved and hooks merged

# Get a project step (for plugin: project)
step_func = config.workflows.get_project_step("ruff_linter")
# Returns callable from .titan/steps/ruff_linter.py
```

**Key methods:**
- `discover()` - Discover all workflows from all sources
- `list_available()` - Get list of workflow names
- `get_workflow(name)` - Get fully resolved ParsedWorkflow
- `get_project_step(name)` - Get project step function from `.titan/steps/`

#### 1.5. ProjectStepSource (`core/workflows/project_step_source.py`)

Discovers and loads Python step functions from `.titan/steps/` directory.

```python
from titan_cli.core.workflows.project_step_source import ProjectStepSource
from pathlib import Path

# Initialize with project root
step_source = ProjectStepSource(Path("/path/to/project"))

# Discover all available project steps
steps = step_source.discover()
# Returns: [StepInfo(name="ruff_linter", path=Path(".titan/steps/ruff_linter.py")), ...]

# Load a specific step function
ruff_linter_func = step_source.get_step("ruff_linter")
# Returns the callable function, dynamically imported
```

**Discovery Convention:**
- Files: `.titan/steps/*.py` (excluding `__*.py`)
- Function name must match filename (e.g., `ruff_linter.py` → `def ruff_linter(...)`)
- Function signature: `def step_name(ctx: WorkflowContext) -> WorkflowResult`

**Caching:**
- Discovered steps are cached in memory
- Loaded functions are cached after first import
- No re-import on subsequent calls (modify file → restart titan)

#### 2. WorkflowExecutor (`engine/workflow_executor.py`)

Executes a `ParsedWorkflow` by iterating through steps, resolving plugin calls, and handling errors.

**Executor Responsibilities:**
- Inject workflow metadata into context (`workflow_name`, `current_step`, `total_steps`)
- Resolve plugin steps and execute them
- Handle parameter substitution (`${variable}`)
- Show error messages for failed steps
- Merge step metadata into `ctx.data`
- Show final workflow success/failure message

For workflow step authoring rules, including how to publish step outputs through result metadata instead of direct `ctx.data` mutation, see [.claude/docs/workflow-step-rules.md](.claude/docs/workflow-step-rules.md).

**What the executor does NOT do:**
- ❌ Does NOT show step headers (steps do this via `ctx.textual.begin_step()`)
- ❌ Does NOT show success/skip messages (steps handle their own UI)
- ❌ Does NOT show step-specific panels or UI

```python
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.engine.builder import WorkflowContextBuilder

# 1. Get workflow from registry
workflow = config.workflows.get_workflow("create-pr")

# 2. Build execution context with dependency injection
ctx = WorkflowContextBuilder(
    plugin_registry=config.registry,
    secrets=secrets,
    ai_config=config.config.ai
).with_ui().with_git().with_github().build()

# 3. Execute workflow
executor = WorkflowExecutor(config.registry)
result = executor.execute(workflow, ctx)

# During execution, the executor:
# - Sets ctx.workflow_name = "create-pr"
# - Sets ctx.total_steps = 7 (number of non-hook steps)
# - Before each step: Sets ctx.current_step = i (1-indexed)
# - After each step: Merges metadata into ctx.data
# - Only shows errors and final workflow status
```

#### 3. WorkflowContext (`engine/context.py`)

Dependency injection container that holds everything a step needs:

```python
@dataclass
class WorkflowContext:
    """
    Context container for workflow execution.

    Provides dependency injection, shared data storage, UI components,
    and workflow metadata for steps.
    """
    # Core dependencies
    secrets: SecretManager

    # Service clients (populated by WorkflowContextBuilder)
    ai: Optional[Any] = None      # AIClient (from builder)
    git: Optional[Any] = None     # GitClient from git plugin
    github: Optional[Any] = None  # GitHubClient from github plugin

    # Textual TUI components
    textual: Optional[TextualComponents] = None
    #   textual.text()           - Normal text
    #   textual.bold_text()      - Bold text
    #   textual.dim_text()       - Dimmed/secondary text
    #   textual.success_text()   - Success message (green)
    #   textual.error_text()     - Error message (red)
    #   textual.warning_text()   - Warning message (yellow)
    #   textual.markdown()       - Render markdown content
    #   textual.mount()          - Mount any Textual widget
    #   textual.ask_text()       - Request text input
    #   textual.ask_multiline()  - Request multiline input
    #   textual.ask_confirm()    - Request Y/N confirmation
    #   textual.ask_selection()  - Multi-select list
    #   textual.ask_choice()     - Single-choice buttons
    #   textual.ask_option()     - Styled option list
    #   textual.loading()        - Loading indicator context manager
    #   textual.begin_step()     - Mark step beginning
    #   textual.end_step()       - Mark step completion

    # Workflow metadata (injected by WorkflowExecutor)
    workflow_name: Optional[str] = None     # Name of current workflow
    current_step: Optional[int] = None      # Current step (1-indexed)
    total_steps: Optional[int] = None       # Total steps in workflow

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    # Helper methods
    def set(self, key: str, value: Any) -> None:
        """Set shared data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get shared data."""
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if key exists in shared data."""
        return key in self.data
```

**Textual TUI Architecture:**

The context provides a single unified UI interface via `ctx.textual`:

- **Display methods**: `text()`, `bold_text()`, `dim_text()`, `success_text()`, `error_text()`, `warning_text()`, `markdown()`, `mount()`
- **Interactive methods**: `ask_text()`, `ask_multiline()`, `ask_confirm()`, `ask_selection()`, `ask_choice()`, `ask_option()`
- **Utility methods**: `loading()`, `begin_step()`, `end_step()`, `scroll_to_end()`
- **Thread-safe**: All methods handle cross-thread communication automatically

**Workflow Metadata:**

The `TextualWorkflowExecutor` automatically injects metadata before running each step:

```python
# Before workflow starts:
ctx.workflow_name = "create-pr"
ctx.total_steps = 7

# Before each step:
ctx.current_step = 1  # Then 2, 3, 4, etc.
```

Steps use `begin_step()` to show step headers:

```python
def my_step(ctx: WorkflowContext) -> WorkflowResult:
    # Show step header
    if ctx.textual:
        ctx.textual.begin_step("My Step")

    # ... rest of step logic

    ctx.textual.end_step("success")
    return Success("Step completed")
```

#### 4. WorkflowResult Types (`engine/results.py`)

Every step must return one of three result types:

```python
from titan_cli.engine import Success, Error, Skip

# Success - step completed
return Success(
    message="Commit created",
    metadata={"commit_hash": "abc123"}  # Auto-merged into ctx.data
)

# Error - step failed (halts workflow by default)
return Error(
    message="Failed to create commit",
    exception=e  # Optional original exception
)

# Skip - step not applicable (not a failure)
return Skip(
    message="No changes to commit",
    metadata={"clean": True}
)
```

### Creating Plugin Steps

All workflow steps are functions that accept a single `WorkflowContext` argument and return a `WorkflowResult` (`Success`, `Error`, or `Skip`). They should be defined in their own modules inside the `steps/` directory of a plugin.

**IMPORTANT: Step UI Responsibility**

Steps are **fully responsible** for their own UI rendering. The `TextualWorkflowExecutor` only:
- Injects metadata (`current_step`, `total_steps`, `workflow_name`) into context
- Shows step headers automatically
- Handles errors (shows error messages for failed steps)
- Merges metadata from successful/skipped steps into `ctx.data`

Steps should:
1. Use `ctx.textual.begin_step()` to mark step start
2. Display their own panels, messages, and UI (success, warnings, info)
3. Use `ctx.textual.end_step()` to mark step completion
4. Return `Success`, `Error`, or `Skip` with appropriate messages

**Step Anatomy:**

```python
# plugins/my-plugin/my_plugin/steps/my_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_cli.ui.tui.widgets import Panel

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Example plugin step with proper UI handling.

    Requires:
        ctx.git: An initialized GitClient.
        ctx.textual: Textual UI context.

    Inputs (from ctx.data):
        my_input_variable (str): A variable needed for this step.

    Outputs (saved to ctx.data):
        my_output_variable (str): A result to be used by later steps.

    Returns:
        Success: If the step completes successfully.
        Error: If an error occurs.
        Skip: If step is not applicable.
    """
    # 1. Check Textual context
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # 2. Show step header
    ctx.textual.begin_step("My Step")

    # 3. Validate inputs
    my_input = ctx.get("my_input_variable")
    if not my_input:
        ctx.textual.end_step("error")
        return Error("Missing my_input_variable in context.")

    # 4. Show UI as needed
    ctx.textual.text(f"Processing: {my_input}")

    # 5. Do the work
    try:
        if ctx.git:
            status = ctx.git.get_status()

            # Show warning panel if needed
            if not status.is_clean:
                ctx.textual.mount(
                    Panel("Warning: Uncommitted changes detected", panel_type="warning")
                )

            # Show success panel when done
            ctx.textual.mount(
                Panel(
                    f"Step completed successfully for branch: {status.branch}",
                    panel_type="success"
                )
            )

    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Step failed: {e}", exception=e)

    # 6. Mark step as complete and return success
    ctx.textual.end_step("success")
    return Success(
        message="Step completed successfully",
        metadata={"my_output_variable": "result_value"}
    )
```

**Registering Steps in Plugin:**

```python
# plugins/my-plugin/my_plugin/plugin.py
class MyPlugin(TitanPlugin):
    def get_steps(self) -> dict:
        from .steps import my_step, another_step
        return {
            "my_step": my_step,
            "another_step": another_step,
        }
```

### Example: Full Workflow Usage

```yaml
# .titan/workflows/deploy.yaml
name: "Deploy to Staging"
description: "Build, test, and deploy to staging environment"

params:
  environment: "staging"
  skip_tests: false

steps:
  - id: install
    name: "Install Dependencies"
    command: "npm install"
    on_error: fail

  - id: test
    name: "Run Tests"
    command: "npm test"
    on_error: "fail"  # Can use params: on_error: "${skip_tests ? 'continue' : 'fail'}"

  - id: build
    name: "Build Application"
    command: "npm run build"

  - id: deploy
    name: "Deploy to Staging"
    command: "./scripts/deploy.sh ${environment}"

  - id: notify
    name: "Notify Team"
    plugin: slack
    step: send_message
    params:
      channel: "#deployments"
      message: "Deployed to ${environment}"
```

**Execute:**

```bash
titan workflow run deploy
```

### Operations Pattern (NEW - 2026-02)

**📖 Complete Guide:** [Operations Pattern Guide](.claude/docs/operations.md)

The **Operations Pattern** is a mandatory architectural pattern for all plugin development that separates business logic from UI orchestration. This separation makes code testable, reusable, and maintainable.

#### Why Operations?

**Problem:** When business logic is mixed with UI code in steps, it becomes:
- Impossible to unit test (requires full workflow context)
- Hard to reuse (logic is tied to specific step UI)
- Difficult to maintain (changes affect both logic and display)
- Prone to duplication (same logic copied across multiple steps)

**Solution:** Extract all business logic to pure, testable operations functions.

#### Architecture

```
plugins/titan-plugin-{name}/
├── titan_plugin_{name}/
│   ├── operations/              # ✨ NEW: Pure business logic
│   │   ├── __init__.py         # Export all operations
│   │   ├── {domain}_operations.py
│   │   └── ...
│   ├── steps/                   # UI orchestration only
│   │   ├── {step_name}_step.py
│   │   └── ...
│   └── ...
├── tests/
│   ├── operations/              # ✨ NEW: Unit tests for operations
│   │   ├── test_{domain}_operations.py
│   │   └── ...
│   └── ...
```

#### Responsibilities

| Layer | Responsibility | Can Access | Cannot Access |
|-------|---------------|------------|---------------|
| **Operations** | Business logic, data transformation | Pure Python, data structures | UI (ctx.textual), workflow context |
| **Steps** | UI orchestration, user interaction | ctx.textual, ctx.data, operations | Complex logic, parsing, algorithms |

#### Quick Example

**❌ Before (Bad):**
```python
# step.py - Business logic mixed with UI
def my_step(ctx: WorkflowContext) -> WorkflowResult:
    ctx.textual.begin_step("Process Data")

    # Business logic mixed in
    data = ctx.get("input")
    items = []
    for line in data.split('\n'):
        if '|' in line:
            parts = line.split('|')
            items.append(parts[0].strip())
    filtered = [x for x in items if len(x) > 5]

    ctx.textual.success_text(f"Processed {len(filtered)} items")
    return Success("Done", metadata={"items": filtered})
```

**✅ After (Good):**
```python
# operations/data_operations.py - Pure business logic
def parse_data(data: str) -> List[str]:
    """Parse pipe-separated data into list of items."""
    items = []
    for line in data.split('\n'):
        if '|' in line:
            parts = line.split('|')
            items.append(parts[0].strip())
    return items

def filter_items(items: List[str], min_length: int = 5) -> List[str]:
    """Filter items by minimum length."""
    return [x for x in items if len(x) >= min_length]

# step.py - Clean UI orchestration
from ..operations import parse_data, filter_items

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    ctx.textual.begin_step("Process Data")

    data = ctx.get("input")

    # Call tested operations
    items = parse_data(data)
    filtered = filter_items(items, min_length=5)

    ctx.textual.success_text(f"Processed {len(filtered)} items")
    return Success("Done", metadata={"items": filtered})
```

#### Implementation Checklist

When creating a new step or refactoring an existing one:

1. **Identify business logic** - Any code that doesn't involve UI
2. **Create operations module** - `operations/{domain}_operations.py`
3. **Write pure functions** - No ctx parameter, no side effects
4. **Add docstrings** - Include examples and type hints
5. **Write unit tests** - Aim for 100% coverage in `tests/operations/`
6. **Export from `__init__.py`** - Make operations discoverable
7. **Update steps** - Import and use operations
8. **Verify coverage** - Run pytest with coverage reporting

#### What to Extract

**✅ Extract to Operations:**
- Data parsing and transformation
- Validation logic
- Calculations and algorithms
- String manipulation
- List/dict processing
- API response parsing

**❌ Keep in Steps:**
- `ctx.textual` calls (text, panels, tables)
- User prompts (ask_text, ask_confirm)
- Loading indicators
- Error message display
- Widget mounting

#### Testing Operations

```bash
# Run operations tests
poetry run pytest plugins/titan-plugin-{name}/tests/operations/ -v

# Check coverage (target: 100%)
poetry run pytest plugins/titan-plugin-{name}/tests/operations/ \
    --cov=plugins/titan-plugin-{name}/titan_plugin_{name}/operations \
    --cov-report=term-missing
```

#### Current Status (2026-02-13)

| Plugin | Operations Modules | Functions | Tests | Coverage |
|--------|-------------------|-----------|-------|----------|
| GitHub | 5 modules | 17 funcs | 40 tests | 99% |
| Git | 3 modules | 13 funcs | 68 tests | 99% |
| Jira | 2 modules | 9 funcs | 47 tests | 100% |
| **Total** | **10 modules** | **39 funcs** | **155 tests** | **99.3%** |

**Benefits Achieved:**
- 295 lines of duplicated code eliminated
- 100% of business logic now testable
- Steps 30-40% smaller and cleaner
- Zero logic duplication across plugins

**📖 For complete implementation guide with real-world examples, see:** [Operations Pattern Guide](.claude/docs/operations.md)

### Workflow Previews

Workflows can be previewed with **mocked data** to test their UI and step flow without performing actual operations. Previews execute **real step functions** with **mocked clients** to ensure consistency between preview and actual execution.

**Preview Structure:**

```
plugins/my-plugin/workflows/__previews__/
├── my_workflow_preview.py      # Preview script for "my-workflow"
└── another_workflow_preview.py
```

**Creating a Preview:**

```python
# plugins/my-plugin/workflows/__previews__/my_workflow_preview.py
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.engine.mock_context import (
    MockGitClient,
    MockAIClient,
    MockGitHubClient,
    MockSecretManager,
)
from titan_cli.engine import WorkflowContext
from titan_cli.engine.ui_container import UIComponents
from titan_cli.engine.views_container import UIViews
from titan_cli.engine.results import Success, Error, Skip


def create_my_workflow_mock_context() -> WorkflowContext:
    """
    Create mock context specifically for this workflow.

    Each preview should define its own mock context with
    workflow-specific data and client configurations.
    """
    # Create UI components
    ui = UIComponents.create()
    views = UIViews.create(ui)

    # Override prompts to auto-confirm (non-interactive preview)
    views.prompts.ask_confirm = lambda question, default=True: True

    # Create mock clients with workflow-specific data
    git = MockGitClient()
    git.current_branch = "feat/my-feature"
    git.main_branch = "main"

    ai = MockAIClient()

    github = MockGitHubClient()
    github.repo_owner = "myorg"
    github.repo_name = "my-repo"

    secrets = MockSecretManager()

    # Build context
    ctx = WorkflowContext(
        secrets=secrets,
        ui=ui,
        views=views
    )

    # Inject mocked clients
    ctx.git = git
    ctx.ai = ai
    ctx.github = github

    return ctx


def preview_workflow():
    """
    Preview my-workflow by executing real steps with mocked context.
    """
    text = TextRenderer()
    spacer = SpacerRenderer()

    # Header
    text.title("My Workflow - PREVIEW")
    text.subtitle("(Executing real steps with mocked data)")
    spacer.line()

    # Create workflow-specific mock context
    ctx = create_my_workflow_mock_context()

    # Import REAL step functions
    from my_plugin.steps.step_one import step_one
    from my_plugin.steps.step_two import step_two

    # Define steps
    steps = [
        ("step_one", step_one),
        ("step_two", step_two),
    ]

    text.info("Executing workflow...")
    spacer.small()

    # Inject workflow metadata (like real executor)
    ctx.workflow_name = "my-workflow"
    ctx.total_steps = len(steps)

    for i, (step_name, step_fn) in enumerate(steps, 1):
        # Inject current step number
        ctx.current_step = i

        # Execute REAL step with mocked data
        result = step_fn(ctx)

        # Only handle errors (steps handle their own success/skip UI)
        if isinstance(result, Error):
            text.error(f"Step '{step_name}' failed: {result.message}")
            break

    spacer.line()
    text.info("(This was a preview - no actual operations performed)")

if __name__ == "__main__":
    preview_workflow()
```

**Running Previews:**

```bash
# Preview a workflow
poetry run titan preview workflow my-workflow
poetry run titan preview workflow create-pr-ai
```

**Mock Clients (`engine/mock_context.py`):**

The `mock_context.py` module provides reusable mock client classes. Each preview creates its own context with customized mock data:

```python
from titan_cli.engine.mock_context import (
    MockGitClient,       # Fake git operations (status, commit, push)
    MockAIClient,        # Returns predefined AI responses
    MockGitHubClient,    # Fake GitHub PR creation
    MockSecretManager,   # Returns fake secrets
)

# Each preview customizes the mocks for its specific scenario
git = MockGitClient()
git.current_branch = "feat/my-feature"  # Customize per workflow
git.main_branch = "main"

ai = MockAIClient()  # Returns workflow-appropriate responses

github = MockGitHubClient()
github.repo_name = "my-repo"  # Customize repo details
```

**Why Preview Execution Matches Real Execution:**

1. **Same step functions** - Previews run the actual step code
2. **Mocked clients only** - Only external dependencies (git, ai, github) are mocked
3. **Real UI rendering** - All panels, text, and formatting are identical
4. **Same executor pattern** - Metadata injection and error handling match production

### UI Output

When executing workflows, steps handle all their own UI rendering:

```
ℹ️ Starting workflow: Create Pull Request
Complete workflow for creating a PR with tests and linting

[1/7] git_status

╭─ ⚠️ Warning ─────────────────────╮
│                                 │
│  You have uncommitted changes.  │
│                                 │
╰─────────────────────────────────╯

╭─ ✅ Success ────────────────────────────────────────────╮
│                                                         │
│  Git status retrieved. Working directory is not clean.  │
│                                                         │
╰─────────────────────────────────────────────────────────╯

[2/7] ai_commit_message

ℹ️ Analyzing changes...
ℹ️ Generating commit message...

Generated Commit Message:
  feat(workflows): add preview system for testing workflow UI

[3/7] create_commit

╭─ ✅ Success ─────────────────────────╮
│                                      │
│  Commit created: abc123              │
│                                      │
╰──────────────────────────────────────╯

[4/7] push

╭─ ✅ Success ─────────────────────────────────────────╮
│                                                      │
│  Pushed to origin/feat/workflow-preview              │
│                                                      │
╰──────────────────────────────────────────────────────╯

✅ Workflow 'Create Pull Request' completed successfully
```

**Note:** The executor only shows the final success message and error messages. All step-specific UI (headers, panels, info messages) is rendered by the steps themselves.

---

## 🔐 Security

- **NEVER commit** `.titan/credentials.toml`
- **API keys** go in global config (`~/.titan/config.toml`), gitignored
- **Secrets** use environment variables when possible
- **Validate all user input** in PromptsRenderer with validators

---

## 📦 Building & Release

### Build package
```bash
poetry build
```

### Publish (maintainers only)
```bash
poetry publish
```

### Version bumping
```bash
poetry version patch  # 0.1.0 → 0.1.1
poetry version minor  # 0.1.1 → 0.2.0
poetry version major  # 0.2.0 → 1.0.0
```

---

## 🤝 Contributing

### Commit Messages
Follow Conventional Commits:
```
feat: Add MenuRenderer component
fix: Fix emoji alignment in TextRenderer
docs: Update AGENTS.md with theming guide
test: Add tests for PromptsRenderer
refactor: Move menu components to views/
```

### Pull Request Checklist
- [ ] Tests pass (`poetry run pytest`)
- [ ] Preview works if UI component (`titan preview <component>`)
- [ ] Follows code style (black, ruff)
- [ ] Uses TextRenderer (no direct print/console in components)
- [ ] Uses messages.py (no hardcoded strings)
- [ ] Uses theme.py styles (no hardcoded colors)
- [ ] Added tests
- [ ] Added preview if UI component
- [ ] Documentation has been updated to reflect the changes.

---

## 🎨 UI Component Reference

### TextRenderer (`ui/components/typography.py`)
```python
text = TextRenderer()
text.title("Main Title")
text.subtitle("Subtitle")
text.body("Normal text", style="dim")
text.success("Success message")
text.error("Error message")
text.warning("Warning message")
text.info("Info message")
text.styled_text(("Part 1", "primary"), ("Part 2", "bold"))
text.line()  # Blank line
text.divider()  # Horizontal line
```

### PanelRenderer (`ui/components/panel.py`)
```python
panel = PanelRenderer()
panel.print("Content", panel_type="success")
panel.print("Content", panel_type="error")
panel.print("Content", panel_type="warning")
panel.print("Content", panel_type="info")
panel.print("Content", title="Custom", style="primary")
```

### TableRenderer (`ui/components/table.py`)
```python
table = TableRenderer()
table.print_table(
    headers=["Name", "Value"],
    rows=[["Item 1", "100"], ["Item 2", "200"]],
    show_lines=True
)
```

### SpacerRenderer (`ui/components/spacer.py`)
```python
spacer = SpacerRenderer()
spacer.line()     # Single line
spacer.small()    # Small gap
spacer.medium()   # Medium gap
spacer.large()    # Large gap
```

### PromptsRenderer (`ui/views/prompts.py`)
```python
prompts = PromptsRenderer()
name = prompts.ask_text("Enter name:", default="John")
confirmed = prompts.ask_confirm("Continue?", default=True)
choice = prompts.ask_choice("Select:", choices=["A", "B", "C"])
number = prompts.ask_int("Enter number:", min_value=1, max_value=10)
item = prompts.ask_menu(menu)  # Returns MenuItem or None
```

### MenuRenderer (`ui/views/menu_components/menu.py`)
```python
from titan_cli.ui.views.menu_components import DynamicMenu, MenuRenderer

# Build menu
menu_builder = DynamicMenu(title="Main Menu", emoji="🚀")
cat_idx = menu_builder.add_category("Actions", emoji="⚡")
menu_builder.add_item(cat_idx, "Action 1", "Description", "action1")
menu = menu_builder.to_menu()

# Render
renderer = MenuRenderer()
renderer.render(menu)
```

---

## 📚 Additional Resources

- **Titan CLI Documentation**: See `DEVELOPMENT.md` for architecture overview
- **Rich Library**: https://rich.readthedocs.io/
- **Typer**: https://typer.tiangolo.com/
- **Pydantic**: https://docs.pydantic.dev/
- **Poetry**: https://python-poetry.org/docs/

---

## 📋 Workflow Quick Reference

### Step Anatomy Checklist

When creating a workflow step, follow this pattern:

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_cli.ui.tui.widgets import Panel

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    """Step docstring with Requires, Inputs, Outputs, Returns."""

    # ✅ 1. Check Textual context
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # ✅ 2. Show step header
    ctx.textual.begin_step("My Step")

    # ✅ 3. Validate requirements
    if not ctx.git:
        ctx.textual.end_step("error")
        return Error("GitClient not available")

    # ✅ 4. Show UI as needed (panels, messages)
    ctx.textual.mount(Panel("Warning message", panel_type="warning"))

    # ✅ 5. Do the work
    try:
        result = ctx.git.some_operation()
    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Operation failed: {e}", exception=e)

    # ✅ 6. Show success UI
    ctx.textual.mount(Panel("Operation completed", panel_type="success"))

    # ✅ 7. Mark step complete and return result
    ctx.textual.end_step("success")
    return Success(
        message="Step completed",
        metadata={"output_key": result}
    )
```

### Textual UI Quick Reference

**Display Methods:**
```python
# Text display
ctx.textual.text("Normal text")
ctx.textual.bold_text("Bold text")
ctx.textual.dim_text("Dimmed text")
ctx.textual.success_text("Success message")
ctx.textual.error_text("Error message")
ctx.textual.warning_text("Warning message")

# Mount widgets
from titan_cli.ui.tui.widgets import Panel, Table
ctx.textual.mount(Panel("Content", panel_type="success"))
ctx.textual.mount(Table(headers=["A", "B"], rows=[...]))

# Markdown
ctx.textual.markdown("## Title\n\n- Item 1\n- Item 2")
```

**Interactive Methods:**
```python
# User input
text = ctx.textual.ask_text("Enter name:", default="")
content = ctx.textual.ask_multiline("Enter description:", default="")
confirmed = ctx.textual.ask_confirm("Continue?", default=True)

# Selection/choices
from titan_cli.ui.tui.widgets import SelectionOption, ChoiceOption, OptionItem
selected = ctx.textual.ask_selection("Select items:", options)
choice = ctx.textual.ask_choice("What to do?", options)
option = ctx.textual.ask_option("Select PR:", options)

# Loading indicator
with ctx.textual.loading("Processing..."):
    # Long operation
    pass
```

### Architecture Principles

**✅ DO:**
- Always check `if ctx.textual:` before using UI
- Use `ctx.textual.begin_step()` at the start of each step
- Use `ctx.textual.end_step()` before returning from step
- Use specific text methods (`success_text()`, `dim_text()`, etc.) instead of `text()` with markup
- Return `Success` with metadata for data sharing
- Use `loading()` context manager for long operations

**❌ DON'T:**
- Don't use `ctx.ui` or `ctx.views` (old Rich UI system - removed)
- Don't use `text(..., markup="dim")` - use `dim_text()` instead
- Don't forget to call `end_step()` before returning
- Don't expect the executor to show step success/skip messages automatically

### Preview System

**Create a workflow preview:**
```python
# plugins/my-plugin/workflows/__previews__/my_workflow_preview.py
from titan_cli.engine.mock_context import MockGitClient, MockAIClient, MockSecretManager
from titan_cli.engine import WorkflowContext
from titan_cli.engine.ui_container import UIComponents
from titan_cli.engine.views_container import UIViews
from titan_cli.engine.results import Error

def create_my_workflow_mock_context():
    """Build workflow-specific mock context."""
    ui = UIComponents.create()
    views = UIViews.create(ui)
    views.prompts.ask_confirm = lambda q, default=True: True

    git = MockGitClient()
    git.current_branch = "feat/my-feature"  # Customize per workflow

    ctx = WorkflowContext(secrets=MockSecretManager(), ui=ui, views=views)
    ctx.git = git
    ctx.ai = MockAIClient()
    return ctx

def preview_workflow():
    ctx = create_my_workflow_mock_context()

    # Import REAL step functions
    from my_plugin.steps import step_one, step_two

    steps = [("step_one", step_one), ("step_two", step_two)]

    # Inject metadata like real executor
    ctx.workflow_name = "my-workflow"
    ctx.total_steps = len(steps)

    for i, (name, fn) in enumerate(steps, 1):
        ctx.current_step = i
        result = fn(ctx)
        if isinstance(result, Error):
            break

if __name__ == "__main__":
    preview_workflow()
```

**Run preview:**
```bash
poetry run titan preview workflow my-workflow
```

---

**Last Updated**: 2026-02-06
**Maintainers**: MasOrange Apps Team (apps-management-stores@masorange.es)
