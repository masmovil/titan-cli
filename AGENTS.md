# AGENTS.md

Documentation for AI coding agents working on Titan CLI.

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

# Project config (.titan/config.toml)
[project]
name = "my-app"
type = "fullstack"

[plugins.github]
enabled = true
org = "myorg"

[plugins.git]
enabled = true
```

### Config Models (Pydantic)

All config is validated using Pydantic models in `core/models.py`:

```python
from pydantic import BaseModel, Field

class ProjectConfig(BaseModel):
    name: str = Field(..., description="Name of the project.")
    type: Optional[str] = Field("generic", description="Type of project.")

class AIConfig(BaseModel):
    provider: str = Field("anthropic", description="AI provider.")
    model: Optional[str] = Field(None, description="AI model.")

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
print(config.config.ai.provider)

# Check enabled plugins
if config.is_plugin_enabled("github"):
    # ... use github plugin
```

---

## 🔌 Plugin System

### Plugin Discovery

Plugins are discovered via **entry points** (not file system):

```toml
# Plugin's pyproject.toml
[project.entry-points."titan.plugins"]
github = "titan_plugin_github:GitHubPlugin"
```

### Installing Plugins

```bash
# Core
pipx install titan-cli

# Add plugin
pipx inject titan-cli titan-plugin-github
```

### Plugin Structure (3-Layer Architecture)

```
plugins/titan-plugin-github/
├── steps/       # LAYER 1: Workflow steps (orchestration)
│   ├── create_pr_step.py
│   └── validate_branch_step.py
├── services/    # LAYER 2: Business logic (wrappers)
│   ├── pr_service.py
│   └── branch_service.py
└── clients/     # LAYER 3: External API (GitHub CLI, API clients)
    └── github_client.py
```

**Layer separation:**
- **Steps**: Orchestration, use WorkflowContext, return WorkflowResult
- **Services**: Business logic, validation, no UI, no workflows
- **Clients**: External API wrappers (gh CLI, HTTP requests)

---

## 🤖 AI Integration

Titan CLI includes a modular AI integration layer that allows for interaction with multiple AI providers (Anthropic, OpenAI, Gemini).

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
└── providers/
    ├── __init__.py
    ├── base.py             # AIProvider abstract base class
    ├── anthropic.py
    ├── gemini.py
    └── openai.py           # Stub for future implementation
```

### Core Components

-   **`AIClient` (`ai/client.py`):** This is the main entry point for using AI functionality. It acts as a facade that reads the user's configuration, retrieves the necessary secrets via `SecretManager`, and instantiates the correct provider.
-   **`AIProvider` (`ai/providers/base.py`):** This is an abstract base class that defines the interface for all AI providers. Each provider implements the `generate()` method to interact with its specific API.

### Configuration

AI configuration is handled via the interactive `titan ai configure` command or by selecting "Configure AI Provider" from the main menu. This command allows the user to:
1.  Select a default provider (Anthropic, OpenAI, or Gemini).
2.  Provide authentication credentials (API Key or OAuth for Gemini), which are stored securely using the `SecretManager`.
3.  Select a default model for the chosen provider, with suggestions for popular models.
4.  Optionally set a custom API endpoint for enterprise use.
5.  Test the connection to ensure everything is set up correctly.

Configuration is stored in the global `~/.titan/config.toml` file:

```toml
[ai]
provider = "anthropic"
model = "claude-3-5-sonnet-20241022"
base_url = "https://custom.endpoint.com" # Optional
temperature = 0.8
max_tokens = 8192
```

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

# 2. Create the AI client
try:
    ai_client = AIClient(config, secrets)
except AIConfigurationError as e:
    # Handle cases where AI is not configured
    print(f"AI not available: {e}")
    return

# 3. Make a request
if ai_client.is_available():
    messages = [AIMessage(role="user", content="Explain the meaning of life.")]
    
    # Simple request
    response = ai_client.generate(messages)
    print(response.content)

    # Request with overrides
    creative_response = ai_client.generate(
        messages,
        temperature=1.2,
        max_tokens=1024
    )
    print(creative_response.content)
```

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

---

## 🚀 Workflow Engine

Titan CLI includes a lightweight, powerful workflow engine for composing and executing sequences of operations. This engine is built on the "Atomic Steps Pattern," where each step in a workflow is a self-contained, testable function.

### File Structure (`engine/`)

The engine is organized as follows:

```
titan_cli/engine/
├── __init__.py              # Public exports
├── results.py               # WorkflowResult types (Success, Error, Skip)
├── context.py               # WorkflowContext (dependency injection container)
├── ui_container.py          # UIComponents container
├── views_container.py       # UIViews container
├── builder.py               # WorkflowContextBuilder (fluent API)
└── workflow.py              # BaseWorkflow (orchestrator)
```

### Core Concepts

#### 1. Steps (`StepFunction`)

A workflow is a list of "steps." Each step is a simple Python function that accepts a `WorkflowContext` and returns a `WorkflowResult`.

```python
from titan_cli.engine import WorkflowContext, Success, Error

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    """Example step."""
    if not ctx.ui:
        return Error("UI components are not available.")
    
    ctx.ui.text.info("Executing my step...")
    # ... perform logic ...
    return Success("My step completed successfully.")
```

#### 2. Workflow Results (`results.py`)

Every step must return one of three `dataclass` objects to signal its outcome:
-   **`Success(message: str, metadata: dict)`**: The step was successful. Any `metadata` provided is automatically merged into the shared `ctx.data` dictionary for subsequent steps to use.
-   **`Error(message: str, exception: Exception)`**: The step failed. By default, this halts the entire workflow. You can optionally pass the original exception.
-   **`Skip(message: str, metadata: dict)`**: The step was not applicable and was skipped. This is not considered a failure. Any `metadata` is also auto-merged.

Module-level helper functions are provided to check the result type: `is_success(result)`, `is_error(result)`, `is_skip(result)`.

#### 3. The Context (`context.py` & `builder.py`)

The `WorkflowContext` is a dependency injection container that holds everything a step might need:
-   Core dependencies (`config`, `secrets`).
-   Service clients (`ai`).
-   UI components, organized by architectural layer.
-   A shared data dictionary (`data`) for passing information between steps.

The `WorkflowContextBuilder` provides a fluent API to construct the context with the required dependencies. It uses a **hybrid DI pattern**:

```python
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.engine import WorkflowContextBuilder

# 1. Initialize core dependencies
config = TitanConfig()
secrets = SecretManager()

# 2. Build context with a fluent API
# Use convenience auto-creation
ctx = WorkflowContextBuilder(config, secrets).with_ui().with_ai().build()

# Use pure DI for testing
mock_ai = MagicMock()
test_ctx = WorkflowContextBuilder(config, secrets).with_ai(ai_client=mock_ai).build()
```

#### 4. UI Architecture in Context

To maintain architectural purity, UI elements in the context are separated into two namespaces:
-   **`ctx.ui`**: Contains basic, pure Rich wrappers from `ui/components/`.
    -   `ctx.ui.text`
    -   `ctx.ui.panel`
    -   `ctx.ui.table`
    -   `ctx.ui.spacer`
-   **`ctx.views`**: Contains composite views from `ui/views/`.
    -   `ctx.views.prompts`
    -   `ctx.views.menu`

#### 5. The Orchestrator (`workflow.py`)

The `BaseWorkflow` class takes a name and a list of steps. Its `.run()` method executes them sequentially, handling logging, error halting, and metadata merging automatically.

### Example Usage

```python
# 1. Define your steps
def validate_user_step(ctx: WorkflowContext):
    name = ctx.views.prompts.ask_text("Enter name:")
    if not name:
        return Error("Name is required.")
    return Success("Name validated", metadata={"user_name": name})

def greet_user_step(ctx: WorkflowContext):
    user_name = ctx.get("user_name")
    ctx.ui.text.success(f"Hello, {user_name}!")
    return Success("Greeting displayed.")

# 2. Build the context
config = TitanConfig()
secrets = SecretManager()
ctx = WorkflowContextBuilder(config, secrets).with_ui().build()

# 3. Define and run the workflow
workflow = BaseWorkflow(
    name="Greeting Workflow",
    steps=[validate_user_step, greet_user_step]
)
result = workflow.run(ctx)

if is_error(result):
    print(f"Workflow failed: {result.message}")
```

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

**Last Updated**: 2025-11-27
**Maintainers**: @finxeto, @raulpedrazaleon
