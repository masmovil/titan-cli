# Guide: Creating a New Visual Component

This guide outlines the best practices and required steps for creating a new, theme-aware visual component for Titan CLI. Following this pattern ensures all UI components are consistent, maintainable, and testable.

We will use the creation of a hypothetical `Alert` component as an example.

## 1. File Structure

First, create the necessary files for your component and its preview.

1.  **Component File:** Create the main component file in `titan_cli/ui/components/`.
    -   Example: `titan_cli/ui/components/alert.py`

2.  **Preview Script:** Create the preview script for your component in the corresponding `__previews__` directory.
    -   Example: `titan_cli/ui/components/__previews__/alert_preview.py`

## 2. Component Implementation (`alert.py`)

Your component should be a class that follows the same dependency injection pattern as `PanelRenderer` and `TextRenderer`.

```python
# titan_cli/ui/components/alert.py

from typing import Optional
from rich.console import Console
from ..console import get_console  # Import the global console getter
from ...messages import msg

class AlertRenderer:
    """
    A component for rendering themed alert boxes.
    """
    def __init__(self, console: Optional[Console] = None):
        """
        Initializes the renderer.

        Args:
            console: A Rich Console instance. If None, uses the global
                     theme-aware console. This allows for dependency injection.
        """
        if console is None:
            console = get_console()
        self.console = console

    def show(self, text: str, style: str = "warning"):
        """
        Displays an alert box with the given text and style.
        
        Args:
            text: The message to display in the alert.
            style: The theme style to use (e.g., "warning", "error").
        """
        # Note: We use the theme-aware console with a semantic style name.
        # We don't use hardcoded colors here.
        self.console.print(f"[{style}]> {text}[/{style}]")

```

**Key Principles:**
-   **Class-based:** Encapsulates logic and state.
-   **Dependency Injection:** The `__init__` takes an optional `console`.
-   **Global Console:** Defaults to `get_console()` to ensure it always uses the theme-aware singleton.
-   **Use Theme Styles:** The component uses semantic style names like `"warning"`, not hardcoded colors like `"yellow"`.

## 3. Preview Script (`alert_preview.py`)

Create a script to visualize your component in isolation. This allows for rapid development and debugging.

```python
# titan_cli/ui/components/__previews__/alert_preview.py

from ..alert import AlertRenderer
from ...typography import title, subtitle, line

def preview_all():
    """Showcases all variations of the Alert component."""
    title("Alert Component Preview")
    subtitle("A demonstration of the AlertRenderer.")
    line()

    renderer = AlertRenderer()

    renderer.show("This is a warning alert.", style="warning")
    renderer.show("This is an error alert.", style="error")
    renderer.show("This is a success alert.", style="success")
    renderer.show("This is an informational alert.", style="info")

if __name__ == "__main__":
    preview_all()
```

## 4. Add the Preview Command

Make your preview accessible via the CLI by adding a command to `titan_cli/preview.py`.

```python
# titan_cli/preview.py

# ... existing imports and commands ...

@preview_app.command("alert")
def preview_alert():
    """Shows a preview of the Alert component."""
    try:
        # The module path matches the file path
        runpy.run_module("titan_cli.ui.components.__previews__.alert_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)
```

## 5. Verify

Run your new preview command from the project root to see your component in action.

```bash
titan preview alert
```

By following these steps, your new component will be perfectly integrated into the project's design system.
