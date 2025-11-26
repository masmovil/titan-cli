"""
Spacer Component Preview

Run this script to preview the Spacer component.
"""

from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.components.typography import TextRenderer

def preview_all():
    """Showcases various spacing options."""
    text = TextRenderer()
    spacer = SpacerRenderer() # Instantiate SpacerRenderer directly

    text.title("Spacer Component Preview")
    text.subtitle("A demonstration of the Spacer component.")
    text.line()

    text.body("Text before small space.")
    spacer.small()
    text.body("Text after small space (1 line).")
    text.line()

    text.body("Text before medium space.")
    spacer.medium()
    text.body("Text after medium space (2 lines).")
    text.line()

    text.body("Text before large space.")
    spacer.large()
    text.body("Text after large space (3 lines).")
    text.line()

    text.body("Text before custom 5 lines space.")
    spacer.lines(5)
    text.body("Text after custom 5 lines space.")
    text.line()

    text.body("Text before single line.")
    spacer.line()
    text.body("Text after single line.")
    text.line()

    text.success("Spacer Preview Complete")

if __name__ == "__main__":
    preview_all()
