

## 🎨 UI Architecture and Theming

The UI components are organized to ensure consistency, reusability, and maintainability.

For a detailed guide on creating new components that follow these patterns, see [Guide: Creating a New Visual Component](docs/guides/creating-visual-components.md).

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
│       └── ... (other complex views)
```

-   **`core/`**: Contains the core business logic and foundational services of the Titan CLI, such as configuration management, plugin discovery, and project scanning.
-   **`commands/`**: Houses the implementations for individual CLI commands (e.g., `titan init`, `titan projects`). Each command or group of commands is typically in its own module.
-   **`ui/`**: Contains all user interface related components, abstracting Rich functionalities for consistent visual output.
    -   **`components/`**: Simple, atomic wrappers around single `rich` elements (e.g., `PanelRenderer`, `TextRenderer`). These are the "building blocks" of your UI.
    -   **`views/`**: More complex, composite UI elements that typically use multiple components. These represent larger portions of the UI (e.g., the application banner, interactive menus).

### 🎨 Centralized Theming (`titan_cli/ui/theme.py`)

All styling throughout the CLI should be driven from a single source of truth: `titan_cli/ui/theme.py`.

This file defines:
-   **`TITAN_THEME`**: A `rich.theme.Theme` object that centralizes custom styles (e.g., `success`, `error`, `info`, `primary`) used by `rich.Console` and components like `PanelRenderer`.
-   **`BANNER_GRADIENT_COLORS`**: A list of hex codes for the application's banner gradient.
-   **`SyntaxTheme` & `ThemeManager`**: Your original implementation for managing syntax highlighting themes (e.g., "dracula", "nord").

**How to use:**
-   **For console output and components:** Ensure your `Console` instance is initialized with `TITAN_THEME` (this is handled by `titan_cli/ui/console.py`). Then, simply use style names (e.g., `console.print("Success!", style="success")`).
-   **For banner:** The `render_ascii_banner` function automatically pulls colors from `BANNER_GRADIENT_COLORS`.
-   **For syntax highlighting:** Use `ThemeManager.get_syntax_theme()` when creating `rich.syntax.Syntax` objects.

### 👁️ Previewing UI Components (`__previews__/` directory)

To efficiently develop and debug UI components, you can preview them in isolation without running the entire CLI application. This is achieved using scripts placed in a `__previews__/` subdirectory alongside the components.

**Structure:**
-   Each component or view (`panel.py`, `banner.py`) that you want to preview will have a corresponding preview script (e.g., `panel_preview.py`) in:
    `titan_cli/ui/components/__previews__/`
    `titan_cli/ui/views/__previews__/`

**How to create a preview:**
1.  Create a file like `panel_preview.py` in the `__previews__/` directory.
2.  Inside this file, import the component you want to test (e.g., `from titan_cli.ui.components.panel import PanelRenderer`).
3.  Write code to instantiate and render your component in various states or with different arguments.

**How to run a preview:**
To run a preview script, use the built-in `titan preview` command:

```bash
# Example for the Panel component
titan preview panel
```

This command is more user-friendly and discoverable. The `preview` subcommand and its associated commands are defined in `titan_cli/preview.py`. To add new preview commands, simply edit that file.
