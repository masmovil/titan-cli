"""
Theme Management

Centralized theme configuration for all Rich-based visual components.
Provides consistent styling across syntax highlighting, panels, and other UI elements.
"""

from enum import Enum
from rich.theme import Theme as RichTheme

# 1. Console Styles Theme
# Defines styles for panels, text, etc.
TITAN_THEME = RichTheme({
    "success": "bold green",
    "error": "bold red",
    "warning": "yellow",
    "info": "cyan",
    "primary": "bold blue",
    "dim": "dim",
})

# 2. Banner Gradient Colors
# Default gradient: blue → purple → pink
BANNER_GRADIENT_COLORS = ["#3B82F6", "#6366F1", "#8B5CF6", "#A855F7", "#C026D3", "#DB2777", "#E11D48"]


# 3. Syntax Highlighting Theme (as you defined it)
class SyntaxTheme(Enum):
    """Available syntax highlighting themes"""
    DRACULA = "dracula"
    MONOKAI = "monokai"
    NORD = "nord"
    GITHUB_DARK = "github-dark"
    ONE_DARK = "one-dark"
    SOLARIZED_DARK = "solarized-dark"
    SOLARIZED_LIGHT = "solarized-light"
    GRUVBOX_DARK = "gruvbox-dark"
    GRUVBOX_LIGHT = "gruvbox-light"


class ThemeManager:
    """Manages global theme configuration for UI components"""

    _current_syntax_theme: SyntaxTheme = SyntaxTheme.DRACULA

    @classmethod
    def get_syntax_theme(cls) -> str:
        """Get current syntax theme name"""
        return cls._current_syntax_theme.value

    @classmethod
    def set_syntax_theme(cls, theme: SyntaxTheme) -> None:
        """Set global syntax theme"""
        cls._current_syntax_theme = theme

    @classmethod
    def set_syntax_theme_by_name(cls, theme_name: str) -> bool:
        """Set syntax theme by name string"""
        try:
            theme = SyntaxTheme(theme_name.lower())
            cls.set_syntax_theme(theme)
            return True
        except ValueError:
            return False

    @classmethod
    def get_available_syntax_themes(cls) -> list[str]:
        """Get list of all available syntax theme names"""
        return [theme.value for theme in SyntaxTheme]