#!/usr/bin/env python3
"""
Panel Component Preview

Run this script to preview all panel variations:
    python3 -m titan_cli.ui.components.__previews__.panel_preview

This is the equivalent of @Preview in Compose - shows components
in isolation without running the full app.
"""

from titan_cli.ui.components.panel import PanelRenderer
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.console import get_console
from titan_cli.messages import msg
from rich import box as rich_box


def preview_all():
    """Preview all panel variations"""
    renderer = PanelRenderer()
    text = TextRenderer()  # ✅ Usa clase en vez de módulo

    text.title("Panel Component Preview")
    text.subtitle("Preview of all panel variations")
    text.line()

    # 1. Info Panel
    text.info("1. Info Panel", show_emoji=False)
    renderer.print(
        "This is an informational message.\nIt uses cyan color and rounded borders.",
        panel_type="info"
    )
    text.line()

    # 2. Success Panel
    text.success("2. Success Panel", show_emoji=False)
    renderer.print(
        "Operation completed successfully!\nGreen border indicates success.",
        panel_type="success"
    )
    text.line()

    # 3. Error Panel
    text.error("3. Error Panel", show_emoji=False)
    renderer.print(
        "An error occurred!\nRed border with heavy box style.",
        panel_type="error"
    )
    text.line()

    # 4. Warning Panel
    text.warning("4. Warning Panel", show_emoji=False)
    renderer.print(
        "Proceed with caution.\nYellow border indicates warning.",
        panel_type="warning"
    )
    text.line()

    # 5. Default Panel
    text.title("5. Default Panel")
    renderer.print(
        "Standard panel with no special styling.",
        panel_type="default",
        title="Custom Title"
    )
    text.line()

    # 6. Custom Styling
    text.title("6. Custom Styling")
    panel = renderer.render(
        "Custom panel with:\n• Primary color\n• Double border\n• Center-aligned title",
        title="Custom Panel",
        style="primary",
        border_style="double",
        title_align="center"
    )
    get_console().print(panel)
    text.line()

    # 7. With Subtitle
    text.title("7. Panel with Subtitle")
    panel = renderer.render(
        "Panel with both title and subtitle.",
        title="Main Title",
        subtitle="Subtitle at bottom",
        style="info",
        border_style="rounded"
    )
    get_console().print(panel)
    text.line()

    # 8. Expanded Panel
    text.title("8. Expanded Panel (Full Width)")
    panel = renderer.render(
        "This panel expands to full console width.",
        title="Full Width",
        style="success",
        expand=True
    )
    get_console().print(panel)
    text.line()

    # 9. Different Border Styles
    text.title("9. Border Styles Comparison")

    borders = [
        ("ascii", rich_box.ASCII),
        ("rounded", rich_box.ROUNDED),
        ("heavy", rich_box.HEAVY),
        ("double", rich_box.DOUBLE),
    ]

    for border_name, border_box in borders:
        panel = renderer.render(
            f"Border style: {border_name}",
            title=border_name.upper(),
            border_style=border_box,
            style="dim"
        )
        get_console().print(panel)
    text.line()

    # 10. Using Messages
    text.title("10. Using Centralized Messages")
    renderer.print(
        msg.Workflow.COMPLETED,
        panel_type="success",
        title="Workflow Status"
    )
    text.line()

    # 11. Long Content
    text.title("11. Panel with Long Content")
    long_content = """
This is a panel with longer content to test wrapping and formatting.

Features:
• Automatic text wrapping
• Markdown formatting support
• Multiple lines
• Proper padding

Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
"""
    renderer.print(
        long_content.strip(),
        panel_type="info",
        title="Documentation"
    )
    text.line()

    text.success("Preview Complete")
    text.line()


def preview_interactive():
    """Interactive preview - prompt for panel type"""
    renderer = PanelRenderer()
    text = TextRenderer()

    text.title("Interactive Panel Preview")
    text.subtitle("Choose a panel type to preview")
    text.line()

    text.body("1. Info")
    text.body("2. Success")
    text.body("3. Error")
    text.body("4. Warning")
    text.body("5. Default")
    text.body("0. Exit")
    text.line()

    while True:
        choice = input("Select option (0-5): ").strip()

        if choice == "0":
            text.subtitle("Exiting preview")
            break
        elif choice == "1":
            renderer.print("This is an info message", panel_type="info")
        elif choice == "2":
            renderer.print("This is a success message", panel_type="success")
        elif choice == "3":
            renderer.print("This is an error message", panel_type="error")
        elif choice == "4":
            renderer.print("This is a warning message", panel_type="warning")
        elif choice == "5":
            renderer.print("This is a default message", panel_type="default")
        else:
            text.error("Invalid choice", show_emoji=False)

        text.line()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        preview_interactive()
    else:
        preview_all()
