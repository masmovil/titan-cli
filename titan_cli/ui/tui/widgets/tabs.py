"""
Tabbed Panel Widget

Titan-styled tabbed container, for screens that configure several independent things and
would otherwise become one long scroll. Each tab gets the full height of the screen, and
switching costs a keystroke instead of navigation.
"""

from textual.widgets import TabbedContent, TabPane


class TabbedPanel(TabbedContent):
    """
    Themed tab strip with one content pane per tab.

    Usage mirrors Textual's own container::

        with TabbedPanel(initial="connections"):
            with TabPanel("Connections", id="connections"):
                yield ...
            with TabPanel("CLI", id="cli"):
                yield ...

    Tab ids are the handle for switching and for querying a pane's contents, so give every
    pane a stable one.
    """

    DEFAULT_CSS = """
    TabbedPanel {
        height: 1fr;
    }

    TabbedPanel > ContentTabs {
        background: $surface;
    }

    TabbedPanel > ContentTabs > #tabs-list {
        min-height: 1;
    }

    TabbedPanel Tab {
        padding: 0 2;
        color: $text-muted;
    }

    TabbedPanel Tab.-active {
        color: $primary;
        text-style: bold;
    }

    TabbedPanel ContentSwitcher {
        height: 1fr;
    }
    """


class TabPanel(TabPane):
    """One tab's content. Always give it an `id`; the label is what the user reads."""

    DEFAULT_CSS = """
    TabPanel {
        padding: 1 0;
    }
    """


__all__ = ["TabbedPanel", "TabPanel"]
