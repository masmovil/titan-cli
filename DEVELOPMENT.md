# DEVELOPMENT.md

> High-Level Architecture Overview for Titan CLI

**For detailed technical documentation, development guides, and best practices, see [AGENTS.md](AGENTS.md).**

---

## 🛠️ Development Setup

### Prerequisites

- Python 3.9+
- pipx

### Installation for Development

```bash
# 1. Clone the repository
git clone https://github.com/your-org/titan-cli.git
cd titan-cli

# 2. Install titan-cli in editable mode
pipx install -e .

# 3. Verify installation
titan --help
```

### Initial Configuration

After installation, configure Titan for your projects:

```bash
# 1. Navigate to your projects directory (parent of all your projects)
cd ~/projects  # or wherever you keep your projects

# 2. Launch Titan interactive menu
titan

# 3. Follow the setup wizard:
#    - Set project root (e.g., ~/projects)
#    - Configure a project from the "Project Management" menu
#    - Install plugins from the "Plugin Management" menu
#      (plugins will be installed from local ./plugins/ directory automatically)
```

**Note:** With editable installation (`-e` flag), Titan will automatically detect local plugins in the repository and install them from there. No need to manually inject plugins.

---

## 🎨 UI Architecture and Theming

The UI components are organized to ensure consistency, reusability, and maintainability.

**For a complete guide on creating new components, theming, and styling patterns, see [AGENTS.md § UI Architecture](AGENTS.md#-ui-architecture).**

### 📦 Component Structure (`titan_cli/`)

The `titan_cli/` package is structured as follows:

```
titan-cli/titan_cli/
├── __init__.py
├── cli.py              # Main CLI application definition
├── preview.py          # Preview commands module
├── messages.py         # Centralized user-facing strings
│
├── core/               # Core application logic and services
│   ├── __init__.py
│   ├── config.py           # TitanConfig: manages global and project config
│   ├── models.py           # Pydantic models for config validation
│   ├── plugin_registry.py  # Discovers installed plugins
│   └── discovery.py        # Project discovery logic
│
├── commands/           # CLI command implementations
│   ├── __init__.py
│   ├── init.py             # 'titan init' command for global setup
│   └── projects.py         # 'titan projects' command for project management
│
├── ui/                 # User Interface components and views
│   ├── __init__.py
│   ├── console.py          # Singleton Rich Console instance
│   ├── theme.py            # Centralized theming configuration
│   │
│   ├── components/         # Basic, reusable UI wrappers
│   │   ├── __init__.py
│   │   ├── panel.py        # Wrapper for rich.panel.Panel
│   │   ├── table.py        # Wrapper for rich.table.Table
│   │   ├── typography.py   # Wrapper for styled text
│   │   ├── spacer.py       # Wrapper for SpacerRenderer (vertical spacing)
│   │   └── ... (other atomic components)
│   │
│   └── views/              # Composite UI elements (e.g., Banner, Menus)
│       ├── __init__.py
│       ├── banner.py       # The application's main banner
│       ├── prompts.py      # Wrapper for interactive prompts
│       └── menu_components/ # Components for interactive menus
│           ├── __init__.py
│           ├── menu_models.py    # Pydantic models for menu structure (Menu, MenuItem, etc.)
│           ├── menu.py      # MenuRenderer class (renders the menu visually)
│           ├── dynamic_menu.py # Helper to build Menu objects programmatically
│           └── __previews__/
│               └── menu_preview.py # Non-interactive preview of the menu
```

**Key architectural principles:**
-   **`core/`**: Contains the core business logic and foundational services of the Titan CLI, such as configuration management, plugin discovery, and project scanning.
-   **`commands/`**: Houses the implementations for individual CLI commands (e.g., `titan init`, `titan projects`). Each command or group of commands is typically in its own module.
-   **`ui/`**: Contains all user interface related components, abstracting Rich functionalities for consistent visual output.
    -   **`components/`**: Pure wrappers around Rich library (no composition of other project components). These are the "building blocks" of your UI.
    -   **`views/`**: Composite components that USE other components, can have business logic. These represent larger portions of the UI (e.g., the application banner, interactive menus).

For detailed structure and layer descriptions, see [AGENTS.md § Project Structure](AGENTS.md#-project-structure).

### 🎨 Centralized Theming (`titan_cli/ui/theme.py`)

All styling is driven from `titan_cli/ui/theme.py`:
-   **`TITAN_THEME`**: Rich theme with semantic styles (`success`, `error`, `info`, `primary`)
-   **`BANNER_GRADIENT_COLORS`**: Banner gradient colors
-   **`ThemeManager`**: Syntax highlighting themes

**Usage:**
- Use semantic style names: `console.print("Success!", style="success")`
- For multi-styled text: Use `TextRenderer.styled_text()`
- Never hardcode colors or styles

For complete theming guide, see [AGENTS.md § Theming & Styling](AGENTS.md#-theming--styling).

### 👁️ Previewing UI Components

Preview components in isolation using `__previews__/` directories:

```bash
# Preview components
titan preview panel
titan preview menu
titan preview typography
```

**Structure:**
- Preview scripts in `__previews__/` subdirectories
- One preview file per component (e.g., `panel_preview.py`)
- Preview commands defined in `titan_cli/preview.py`

For complete preview guide, see [AGENTS.md § Creating a New Component](AGENTS.md#-ui-architecture).
