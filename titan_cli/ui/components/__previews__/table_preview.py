"""
Table Component Preview

Run this script to preview the TableRenderer component.
"""

from titan_cli.ui.components.table import TableRenderer
from titan_cli.ui.components.typography import TextRenderer

def preview_all():
    """Showcases various table styles."""
    text = TextRenderer()
    renderer = TableRenderer()

    text.title("Table Component Preview")
    text.subtitle("A demonstration of the TableRenderer component.")
    text.line()

    # Basic Table
    text.title("1. Basic Table")
    headers = ["ID", "Name", "Status"]
    rows = [
        ["101", "Alice", "[green]Active[/green]"],
        ["102", "Bob", "[yellow]Pending[/yellow]"],
        ["103", "Charlie", "[red]Inactive[/red]"],
    ]
    renderer.print_table(headers=headers, rows=rows, title="User Status")
    text.line()

    # Table with Lines
    text.title("2. Table with Lines")
    renderer.print_table(
        headers=headers,
        rows=rows,
        title="User Status (with lines)",
        show_lines=True
    )
    text.line()

    # Table with different box style
    text.title("3. Heavy Box Style")
    renderer.print_table(
        headers=headers,
        rows=rows,
        title="User Status (heavy box)",
        box_style="heavy"
    )
    text.line()
    
    # Table with alternating row styles
    text.title("4. Alternating Row Styles")
    renderer.print_table(
        headers=headers,
        rows=rows,
        title="User Status (alternating rows)",
        row_styles=["dim", "none"]
    )
    text.line()

    text.success("Table Preview Complete")

if __name__ == "__main__":
    preview_all()