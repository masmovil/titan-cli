# Guide: Creating a New Visual Component

This guide outlines the best practices and required steps for creating a new, theme-aware visual component for Titan CLI. Following this pattern ensures all UI components are consistent, maintainable, and testable.

## 1. File Structure

First, create the necessary files for your component and its preview.

1.  **Component File:** New components should live in `titan_cli/ui/components/`.
    -   Example: `titan_cli/ui/components/my_component.py`
2.  **Preview Script:** Create a corresponding preview script in `titan_cli/ui/components/__previews__/`.
    -   Example: `titan_cli/ui/components/__previews__/my_component_preview.py`

## 2. Component Implementation Principles

Your component should be a class (e.g., `MyComponentRenderer`) that follows these key principles:

-   **Class-based:** Encapsulates logic and state.
-   **Dependency Injection:** The `__init__` method must accept a `console: Optional[Console] = None` argument. It should default to using the global `get_console()` instance if none is provided. This is crucial for theme awareness and testability.
-   **Use Theme Styles:** The component must use semantic style names defined in `titan_cli/ui/theme.py` (e.g., `"success"`, `"primary"`) instead of hardcoded colors like `"green"`.
-   **Use Centralized Messages:** All user-visible text (emojis, status messages) should be imported from `titan_cli.messages.msg`.

---

## Example 1: `TableRenderer` Component

Here's how the `TableRenderer` component is implemented following the above principles.

### `table.py` Implementation

```python
# titan_cli/ui/components/table.py

from typing import List, Optional, Literal, Union
from rich.table import Table
from rich.console import Console
from rich import box as rich_box
from ..console import get_console

class TableRenderer:
    def __init__(self, console: Optional[Console] = None):
        if console is None:
            console = get_console()
        self.console = console

    def render(self, headers: List[str], rows: List[List[str]], **kwargs) -> Table:
        # ... implementation ...
        return table
```

### `table_preview.py` Script

```python
# titan_cli/ui/components/__previews__/table_preview.py

from titan_cli.ui.components.table import TableRenderer
from titan_cli.ui.components.typography import TextRenderer

def preview_all():
    text = TextRenderer()
    renderer = TableRenderer()
    text.title("Table Component Preview")
    # ... render tables ...

if __name__ == "__main__":
    preview_all()
```

---

## Example 2: `SpacerRenderer` Component

Here is a simpler component example, the `SpacerRenderer`.

### `spacer.py` Implementation

```python
# titan_cli/ui/components/spacer.py

from typing import Optional
from rich.console import Console
from ..console import get_console

class SpacerRenderer:
    def __init__(self, console: Optional[Console] = None):
        if console is None:
            console = get_console()
        self.console = console

    def line(self) -> None:
        self.console.print()

    def lines(self, count: int = 1) -> None:
        for _ in range(count):
            self.console.print()
```

### `spacer_preview.py` Script

```python
# titan_cli/ui/components/__previews__/spacer_preview.py

from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.components.typography import TextRenderer

def preview_all():
    text = TextRenderer()
    spacer = SpacerRenderer()
    text.title("Spacer Component Preview")
    text.body("Text before small space.")
    spacer.small() # .small() is an alias for .lines(1)
    text.body("Text after small space.")
    # ... more examples ...

if __name__ == "__main__":
    preview_all()
```

---

## 3. Add the Preview Command

Make your preview accessible via the CLI by adding a command to `titan_cli/preview.py`.

```python
# titan_cli/preview.py

# ... existing imports and commands ...

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

By following these steps, your new component will be perfectly integrated into the project's design system.