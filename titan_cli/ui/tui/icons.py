"""
Icon Constants for TUI

Centralized icon definitions using Unicode emojis for maximum compatibility.
All TUI screens and widgets should import icons from here.
"""


class Icons:
    """
    Icon constants for Textual TUI.

    Uses Unicode emojis that work across all terminals without special fonts.
    Organized by category for easy discovery.
    """

    # Status indicators
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "🟡"
    INFO = "🔵"
    QUESTION = "❓"

    # Progress states
    PENDING = "⏸ "
    RUNNING = "⏳"
    COMPLETED = SUCCESS  # Alias
    FAILED = ERROR  # Alias
    SKIPPED = "⏭ "

    # Workflow & execution
    WORKFLOW = "⚡"
    STEP = "→"
    NESTED_WORKFLOW = "🔄"

    # Navigation
    BACK = "←"
    FORWARD = "→"
    UP = "↑"
    DOWN = "↓"
    LEFT = "←"
    RIGHT = "→"

    # Resources
    FOLDER = "📁"
    FILE = "📄"
    PLUGIN = "🔌"
    PACKAGE = "📦"
    PROJECT = "📂"

    # Git & VCS
    GIT_BRANCH = "🌿"
    GIT_COMMIT = "💾"
    GIT_PULL = "⬇ "
    GIT_PUSH = "⬆ "

    # AI & Automation
    AI = "🤖"
    AI_CONFIG = "🧠"
    ROBOT = "🤖"
    SPARKLES = "✨"

    # General UI
    MENU = "☰"
    SETTINGS = "⚙ "
    SEARCH = "🔍"
    STAR = "⭐"
    STAR_OUTLINE = "☆"
    CHECK = "✓"
    CROSS = "✗"
    BULLET = "•"
    ARROW = "→"
