# Guide: Creating a New Visual Component

This guide outlines the best practices and required steps for creating a new, theme-aware visual component for Titan CLI. Following this pattern ensures all UI components are consistent, maintainable, and testable.

## 1. File Structure

First, create the necessary files for your component and its preview.

1.  **Component File:**
    -   Pure, atomic components (no dependencies on other components) live in `titan_cli/ui/components/`.
    -   Composite components (that use other components) live in `titan_cli/ui/views/`.
2.  **Preview Script:** Create a corresponding preview script in the `__previews__/` subdirectory (e.g., `titan_cli/ui/components/__previews__/my_component_preview.py`).

## 2. Component Implementation Principles

Your component should be a class (e.g., `MyComponentRenderer`) that follows these key principles:

-   **Class-based:** Encapsulates logic and state.
-   **Dependency Injection:** The `__init__` method must accept dependencies like `console: Optional[Console] = None`. It should default to using a global getter (e.g., `get_console()`) if none is provided.
-   **Use Theme & Messages:** The component must use semantic style names from `theme.py` and user-facing strings from `messages.py`. No hardcoded colors or text.

---

## Component Examples

Below are the core UI components, which serve as templates for creating new ones. Each component has a brief description and links to its full implementation and preview script.

### Example 1: `TextRenderer` (Component)

-   **Responsibility:** Renders all themed text, including titles, subtitles, and semantic messages (`success`, `error`, etc.).
-   **Source:** [`titan_cli/ui/components/typography.py`](../../titan_cli/ui/components/typography.py)
-   **Preview:** [`titan_cli/ui/components/__previews__/typography_preview.py`](../../titan_cli/ui/components/__previews__/typography_preview.py)

### Example 2: `PanelRenderer` (Component)

-   **Responsibility:** Renders themed panels with predefined styles for different states.
-   **Source:** [`titan_cli/ui/components/panel.py`](../../titan_cli/ui/components/panel.py)
-   **Preview:** [`titan_cli/ui/components/__previews__/panel_preview.py`](../../titan_cli/ui/components/__previews__/panel_preview.py)

### Example 3: `TableRenderer` (Component)

-   **Responsibility:** Renders themed tables with configurable styles.
-   **Source:** [`titan_cli/ui/components/table.py`](../../titan_cli/ui/components/table.py)
-   **Preview:** [`titan_cli/ui/components/__previews__/table_preview.py`](../../titan_cli/ui/components/__previews__/table_preview.py)

### Example 4: `SpacerRenderer` (Component)

-   **Responsibility:** Manages vertical whitespace in the console output.
-   **Source:** [`titan_cli/ui/components/spacer.py`](../../titan_cli/ui/components/spacer.py)
-   **Preview:** [`titan_cli/ui/components/__previews__/spacer_preview.py`](../../titan_cli/ui/components/__previews__/spacer_preview.py)

### Example 5: `PromptsRenderer` (View / Composite Component)

-   **Responsibility:** Handles all interactive user input (text, confirmation, choices, etc.). It's a "view" because it's a composite component that uses `TextRenderer` to display its internal messages.
-   **Source:** [`titan_cli/ui/views/prompts.py`](../../titan_cli/ui/views/prompts.py)
-   **Preview:** [`titan_cli/ui/views/__previews__/prompts_preview.py`](../../titan_cli/ui/views/__previews__/prompts_preview.py)

---

## 3. Add the Preview Command

Make your preview accessible via the CLI by adding a command to `titan_cli/preview.py`.

```python
@preview_app.command("my_component")
def preview_my_component():
    """Shows a preview of MyComponent."""
    try:
        runpy.run_module("titan_cli.ui.components.__previews__.my_component_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)
```

## 4. Verify

Run your new preview command from the project root to see your component in action.

```bash
titan preview my_component
```