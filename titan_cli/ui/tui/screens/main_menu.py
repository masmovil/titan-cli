"""
Main Menu Screen

The primary navigation screen for Titan TUI.
"""

import asyncio

from textual.app import ComposeResult
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from textual.containers import Container

from titan_cli import __version__
from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import StatusBarWidget
from titan_cli.core.plugins.community_sources import (
    CommunityPluginRecord,
    PluginChannel,
    get_github_token,
    check_for_updates,
)
from .base import BaseScreen

from .ai_config import AIConfigScreen
from .plugin_management import PluginManagementScreen

class MainMenuScreen(BaseScreen):
    """
    Main menu screen with navigation options.

    Displays the primary actions available in Titan:
    - Project Management
    - Workflows
    - Plugin Management
    - AI Configuration
    - Switch Project
    - Exit
    """

    def __init__(self, config, **kwargs):
        """Initialize main menu with version in title."""
        super().__init__(
            config,
            title=f"Titan CLI v{__version__}",
            show_back=False,
            **kwargs
        )

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    CSS = """
    MainMenuScreen {
        align: center middle;
    }

    #menu-container {
        width: 70%;
        height: 1fr;
        background: $surface-lighten-1;
        border: solid $primary;
        margin: 1;
        padding: 1 0;
    }

    #menu-title {
        text-align: center;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    OptionList {
        height: auto;
        border: none;
        background: $surface-lighten-1;
    }

    OptionList:focus {
        border: none;
        background: $surface-lighten-1;
    }

    OptionList > .option-list--option {
        padding: 1 2;
        background: $surface-lighten-1;
        border-left: none;
    }

    OptionList > .option-list--option-highlighted {
        background: $primary;
        border-left: none;
    }

    OptionList:focus > .option-list--option {
        border-left: none;
    }

    OptionList:focus > .option-list--option-highlighted {
        border-left: none;
    }

    """

    def compose_content(self) -> ComposeResult:
        """Compose the main menu content."""
        with Container(id="menu-container"):

            # Build menu options
            options = []

            # Only show Workflows if there are enabled plugins
            installed_plugins = self.config.registry.list_installed()
            enabled_plugins = [
                p for p in installed_plugins if self.config.is_plugin_enabled(p)
            ]
            if enabled_plugins:
                options.append(Option(f"{Icons.WORKFLOW} Workflows", id="run_workflow"))

            options.extend(
                [
                    Option(f"{Icons.PLUGIN} Plugin Management", id="plugin_management"),
                    Option(f"{Icons.AI_CONFIG}  AI Configuration", id="ai_config"),
                ]
            )

            yield OptionList(*options)

    def on_mount(self) -> None:
        for message in self.config.get_plugin_sync_events():
            self.app.notify(message, severity="information", timeout=6)
        self.run_worker(self._check_plugin_updates(), exclusive=False)

    async def _check_plugin_updates(self) -> None:
        records = self._get_project_stable_records()
        if not records:
            return
        token = await asyncio.to_thread(get_github_token)
        updates = await asyncio.to_thread(check_for_updates, records, token)
        for record, latest in updates:
            self.app.notify(
                f"Update available for '{record.titan_plugin_name}': "
                f"{record.requested_ref} → {latest}\n"
                "Go to Plugin Management to update.",
                severity="warning",
                timeout=12,
            )

    def _get_project_stable_records(self) -> list[CommunityPluginRecord]:
        """Return synthetic records for project-pinned community plugins."""
        records: list[CommunityPluginRecord] = []
        for plugin_name in self.config.get_enabled_plugins():
            repo_url = self.config.get_project_plugin_repo_url(plugin_name)
            resolved_commit = self.config.get_project_plugin_resolved_commit(plugin_name)
            if not repo_url or not resolved_commit:
                continue
            records.append(
                CommunityPluginRecord(
                    repo_url=repo_url,
                    package_name=plugin_name,
                    titan_plugin_name=plugin_name,
                    installed_at="",
                    channel=PluginChannel.STABLE,
                    dev_local_path=None,
                    requested_ref=self.config.get_project_plugin_requested_ref(plugin_name) or resolved_commit,
                    resolved_commit=resolved_commit,
                )
            )
        return records

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle menu option selection."""
        action = event.option.id

        if action == "exit":
            self.app.exit()
        elif action == "projects":
            self.handle_projects_action()
        elif action == "run_workflow":
            self.handle_workflow_action()
        elif action == "plugin_management":
            self.handle_plugin_management_action()
        elif action == "ai_config":
            self.handle_ai_config_action()

    def handle_projects_action(self) -> None:
        """Handle Project Management action."""
        self.app.notify("Project management - Coming soon!")

    def handle_workflow_action(self) -> None:
        """Handle Workflows action."""
        from .workflows import WorkflowsScreen

        self.app.push_screen(WorkflowsScreen(self.config))

    def handle_plugin_management_action(self) -> None:
        """Handle Plugin Management action."""
        self.app.push_screen(PluginManagementScreen(self.config))

    def handle_ai_config_action(self) -> None:
        """Handle AI Configuration action."""
        def on_ai_config_closed(result) -> None:
            """Callback when AI config screen is closed."""
            # Refresh status bar with latest config
            try:
                # Reload config from disk
                self.config.load()

                status_bar = self.query_one("#status-bar", StatusBarWidget)
                self._update_status_bar(status_bar)
            except Exception as e:
                self.app.notify(f"Error refreshing status bar: {e}", severity="error")

        self.app.push_screen(AIConfigScreen(self.config), callback=on_ai_config_closed)

    def handle_switch_project_action(self) -> None:
        """Handle Switch Project action."""
        self.app.notify("Switch project - Coming soon!")

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
