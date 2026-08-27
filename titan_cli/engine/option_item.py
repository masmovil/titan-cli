"""
Option item for single-choice selection prompts (ctx.textual.ask_option).

Defined in the engine layer (not titan_cli.ui.tui) because engine steps need to
build option lists without depending on the UI layer, which itself depends on
the engine (workflow context, results). titan_cli.ui.tui.widgets re-exports this
same class for backward compatibility with existing imports.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class OptionItem:
    """
    Option for single-choice selection prompts.

    Attributes:
        value: The value to return when selected (can be any type)
        title: The title text (rendered in bold)
        description: Optional description text (rendered in dim)
    """
    value: Any
    title: str
    description: str = ""


__all__ = ["OptionItem"]
