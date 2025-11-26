"""
Typography Component Preview

Run this script to preview all typography variations:
    poetry run python -m titan_cli.ui.components.__previews__.typography_preview

This demonstrates the centralized text styling.
"""

from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg


def preview_all():
    """Preview all typography variations"""
    text = TextRenderer() # Instantiate the class

    text.title("Typography Component Preview")
    text.subtitle("Showcasing all text styles from the typography module.")
    text.line(2)

    # Title and Subtitle
    text.title("1. Titles & Subtitles")
    text.body("Using text.title() and text.subtitle():")
    text.line()
    text.title("Main Application Title", justify="center")
    text.subtitle("A centered subtitle for context.", justify="center")
    text.line()

    # Body Text
    text.title("2. Body Text")
    text.body("Standard body text using text.body():")
    text.line()
    text.body("This is a piece of standard body text. It should appear without any special styling unless inherited from the console's default.")
    text.body(f"You can also include variables like the current version: {msg.CLI.VERSION.format(version='0.1.0')}")
    text.line()

    # Semantic Messages with Emojis
    text.title("3. Semantic Messages (with Emojis)")
    text.body("Messages with default emojis using text.success(), error(), etc.:")
    text.line()
    text.success("Operation completed successfully.")
    text.info("This is an important piece of information.")
    text.warning("Something might be wrong here, proceed with caution.")
    text.error("An unrecoverable error has occurred.")
    text.line()

    # Semantic Messages without Emojis
    text.title("4. Semantic Messages (without Emojis)")
    text.body("Messages with emojis disabled using show_emoji=False:")
    text.line()
    text.success("Configuration loaded", show_emoji=False)
    text.info("Checking dependencies", show_emoji=False)
    text.warning("Disk space low", show_emoji=False)
    text.error("Build failed", show_emoji=False)
    text.line()

    # Line breaks
    text.title("5. Line Breaks")
    text.body("Using text.line(count):")
    text.body("Line above this.")
    text.line(3)
    text.body("Line below this (after 3 blank lines).")
    text.line()

    text.success("Typography Preview Complete")
    text.line()


if __name__ == "__main__":
    preview_all()
