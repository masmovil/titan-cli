"""
Chip Widget

A short, self-contained label with a tinted background — for a fact about the surrounding
output rather than part of it. Sized to its content, so it reads as a tag and not as another
line of text.

The first use is naming which AI served a step: that line was previously dim, i.e. styled
exactly like the progress chatter around it, which made "who answered this?" invisible in
the one place the user is looking.
"""

from textual.widgets import Static


class Chip(Static):
    """
    A tinted, content-width tag.

    Args:
        label: Text inside the chip.
        variant: Visual style — "primary" (default), "success", "warning", "error".
    """

    DEFAULT_CSS = """
    Chip {
        width: auto;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        color: $primary;
        background: $primary 20%;
        text-style: bold;
    }

    Chip.success {
        color: $success;
        background: $success 20%;
    }

    Chip.warning {
        color: $warning;
        background: $warning 20%;
    }

    Chip.error {
        color: $error;
        background: $error 20%;
    }
    """

    def __init__(self, label: str, variant: str = "primary", **kwargs):
        super().__init__(label, **kwargs)
        if variant != "primary":
            self.add_class(variant)
