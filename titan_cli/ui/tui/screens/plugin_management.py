"""
Plugin Management Screen

Screen for managing installed plugins:
- Enable/disable plugins
- Configure plugin settings
- View plugin status
"""

from textual.app import ComposeResult
from pathlib import Path

from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from textual.containers import Container, Horizontal, VerticalScroll
from textual.binding import Binding

from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import (
    Button,
    Text,
    DimText,
    BoldText,
    BoldPrimaryText,
    WarningText,
    SegmentedSwitch,
    SegmentedSwitchOption,
    DevSourcePathModal,
)
from .base import BaseScreen
from .install_plugin_screen import InstallPluginScreen
from titan_cli.core.plugins.local_sources import get_local_plugin_validation_error
from titan_cli.core.plugins.community_sources import (
    CommunityPluginRecord,
    PluginChannel,
    check_for_update,
    get_github_token,
)
from titan_cli.core.logging import get_logger
import asyncio
import tomli
import tomli_w

from .plugin_config_resolver import plugin_has_config_ui, resolve_plugin_config_screen

logger = get_logger(__name__)



class PluginManagementScreen(BaseScreen):
    """
    Plugin management screen for enabling/disabling and configuring plugins.

    Displays all installed plugins with their current status and allows:
    - Toggle enable/disable state
    - Configure plugin settings via wizard
    - View plugin information
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        Binding("e", "toggle_plugin", "Enable/Disable"),
        Binding("c", "configure_plugin", "Configure"),
        Binding("d", "set_dev_source", "Set Dev Path"),
        Binding("i", "install_plugin", "Install"),
        Binding("r", "remove_plugin_from_project", "Remove from Project"),
        Binding("u", "uninstall_plugin", "Uninstall"),
        Binding("U", "update_plugin", "Update"),
    ]

    CSS = """
    PluginManagementScreen {
        align: center middle;
    }

    #plugin-container {
        width: 100%;
        height: 1fr;
        background: $surface-lighten-1;
    }

    #plugin-container Horizontal {
        width: 100%;
        height: 1fr;
        padding: 1;
    }

    #left-panel {
        width: 20%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #left-panel OptionList {
        height: 1fr;
        width: 100%;
        padding: 1;
    }

    #install-plugin-button {
        width: 100%;
        margin: 1 1 1 1;
    }

    #left-panel OptionList > .option-list--option {
        padding: 1;
    }

    #right-panel {
        width: 80%;
        height: 1fr;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #plugin-details {
        height: 100%;
        width: 100%;
        padding: 1;
    }

    #details-content {
        height: auto;
        width: 100%;
    }

    #details-content Text {
        height: 1;
    }

    #details-content > * {
        margin: 0;
    }

    #details-content Horizontal {
        height: auto;
        width: 100%;
        layout: horizontal;
    }

    #details-content Horizontal > * {
        height: auto;
    }

    .source-switch-row {
        height: 3;
        width: auto;
        align: left middle;
        margin-top: 1;
    }

    .source-switch-row DimText {
        width: auto;
        height: 3;
        margin-right: 1;
        margin-top: 1;
        content-align: left middle;
    }

    .source-switch-row SegmentedSwitch {
        height: 3;
        content-align: left middle;
    }

    .button-container {
        height: auto;
        min-height: 5;
        width: 100%;
        padding: 1 1 2 1;
        margin-top: 1;
        background: $surface-lighten-1;
        align: right middle;
    }

    .button-container Button {
        margin-left: 1;
    }
    """

    def __init__(self, config):
        super().__init__(
            config,
            title=f"{Icons.PLUGIN} Plugin Management",
            show_back=True
        )
        self.selected_plugin = None
        self.selected_missing_plugin = None
        self.installed_plugins = []
        self._source_switch_plugin = None

    def compose_content(self) -> ComposeResult:
        """Compose the plugin management screen."""
        with Container(id="plugin-container"):
            with Horizontal():
                # Left panel: Plugin list + install button
                left_panel = Container(id="left-panel")
                left_panel.border_title = "Installed Plugins"
                with left_panel:
                    yield OptionList(id="plugin-list")
                    yield Button(f"{Icons.PLUGIN} Install Plugin", variant="primary", id="install-plugin-button")

                # Right panel: Plugin details and actions
                right_panel = Container(id="right-panel")
                right_panel.border_title = "Plugin Details"
                with right_panel:
                    with VerticalScroll(id="plugin-details"):
                        yield Container(id="details-content")


    def on_mount(self) -> None:
        """Initialize the screen with plugin list."""
        self._load_plugins()

    def on_screen_resume(self) -> None:
        """Refresh plugin status after returning from child screens."""
        super().on_screen_resume()
        try:
            self._load_plugins()
        except Exception:
            pass

    def _load_plugins(self) -> None:
        """Load and display installed plugins."""
        self.installed_plugins = self.config.registry.list_installed()

        # Repopulate the one list that is already in the tree. Replacing the widget looked
        # equivalent but was not: Textual completes `remove()` on a later frame while `mount()`
        # lands immediately, so loading twice in quick succession - which is exactly what
        # on_mount plus on_screen_resume do - left both lists on screen.
        plugin_list = self.query_one("#plugin-list", OptionList)
        selected_id = self.selected_plugin
        if self.selected_missing_plugin:
            selected_id = f"missing:{self.selected_missing_plugin}"

        options = []

        # Find plugins enabled in config but not installed
        missing_plugins = []
        if self.config.config and self.config.config.plugins:
            for plugin_name, plugin_cfg in self.config.config.plugins.items():
                if getattr(plugin_cfg, "enabled", False) and plugin_name not in self.installed_plugins:
                    missing_plugins.append(plugin_name)

        if not self.installed_plugins and not missing_plugins:
            plugin_list.clear_options()
            plugin_list.add_option(Option("No plugins installed", id="none", disabled=True))
            self._show_no_plugin_selected()
            return

        # Add installed plugin options
        for plugin_name in self.installed_plugins:
            is_enabled = self.config.is_plugin_enabled(plugin_name)
            needs_attention = self._plugin_needs_attention(plugin_name, is_enabled)
            if needs_attention:
                status_icon = Icons.WARNING
                status_text = "Setup needed"
            else:
                status_icon = Icons.SUCCESS if is_enabled else Icons.ERROR
                status_text = "Enabled" if is_enabled else "Disabled"

            active_rec = self._build_stable_record(plugin_name)
            badge = " [community]" if active_rec else ""

            options.append(
                Option(
                    f"{status_icon} {plugin_name}{badge} - {status_text}",
                    id=plugin_name,
                )
            )

        # Add missing plugin options
        for plugin_name in missing_plugins:
            options.append(
                Option(
                    f"{Icons.WARNING} {plugin_name} - Not installed",
                    id=f"missing:{plugin_name}"
                )
            )

        plugin_list.clear_options()
        plugin_list.add_options(options)

        # Select first plugin by default
        all_plugins = self.installed_plugins + [f"missing:{p}" for p in missing_plugins]
        if all_plugins:
            target = selected_id if selected_id in all_plugins else all_plugins[0]
            plugin_list.highlighted = all_plugins.index(target)
            plugin_list.refresh(repaint=True, layout=True)
            if target.startswith("missing:"):
                plugin_name = target.removeprefix("missing:")
                self.selected_plugin = None
                self.selected_missing_plugin = plugin_name
                self._show_plugin_missing(plugin_name)
            else:
                self.selected_missing_plugin = None
                self.selected_plugin = target
                self._show_plugin_details(target)

    def _plugin_needs_attention(self, plugin_name: str, is_enabled: bool) -> bool:
        """Return whether a plugin is enabled but still needs user attention."""
        if not is_enabled or plugin_name != "slack":
            return False

        project_name = self.config.get_project_name()
        if not project_name:
            return False

        token_key = f"{project_name}_slack_user_token"
        broker = self.config.broker_factory.for_plugin("slack")
        return not broker.exists(token_key)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle plugin selection (Enter key)."""
        if event.option.id == "none":
            return

        if event.option.id.startswith("missing:"):
            self.selected_plugin = None
            self.selected_missing_plugin = event.option.id.removeprefix("missing:")
            self._show_plugin_missing(self.selected_missing_plugin)
            return

        self.selected_missing_plugin = None
        self.selected_plugin = event.option.id
        self._show_plugin_details(self.selected_plugin)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle plugin highlight change (arrow keys navigation)."""
        if event.option.id == "none":
            return

        if event.option.id.startswith("missing:"):
            self.selected_plugin = None
            self.selected_missing_plugin = event.option.id.removeprefix("missing:")
            self._show_plugin_missing(self.selected_missing_plugin)
            return

        self.selected_missing_plugin = None
        self.selected_plugin = event.option.id
        self._show_plugin_details(self.selected_plugin)

    def _show_no_plugin_selected(self) -> None:
        """Display message when no plugin is selected."""
        details = self.query_one("#details-content", Container)
        details.remove_children()

        details.mount(DimText("No plugins installed."))
        details.mount(DimText("Plugins are automatically discovered from installed packages."))

    def _show_plugin_missing(self, plugin_name: str) -> None:
        """Display details for a plugin enabled in config but not installed."""
        details = self.query_one("#details-content", Container)
        details.remove_children()

        details.mount(BoldPrimaryText(plugin_name))
        details.mount(Text(""))
        details.mount(WarningText(f"{Icons.WARNING} Not installed"))
        details.mount(Text(""))
        details.mount(DimText(
            f"The plugin '{plugin_name}' is enabled in your project config "
            "but is not installed in this Titan environment."
        ))
        details.mount(Text(""))
        details.mount(DimText("Press i to add it from a community plugin URL."))
        details.mount(DimText("Press r to remove it from this project's config."))
        details.mount(Text(""))
        details.mount(Horizontal(
            Button("Install Plugin", variant="primary", id="install-plugin-button-details"),
            Button("Remove from Project", variant="error", id="remove-plugin-button-details"),
            classes="button-container"
        ))

    def _show_plugin_details(self, plugin_name: str) -> None:
        """Display details for the selected plugin."""
        if not plugin_name or plugin_name == "none":
            self._show_no_plugin_selected()
            return

        plugin = self.config.registry._plugins.get(plugin_name)

        # Get plugin info
        is_enabled = self.config.is_plugin_enabled(plugin_name)
        needs_attention = self._plugin_needs_attention(plugin_name, is_enabled)

        # Clear and rebuild details
        details = self.query_one("#details-content", Container)
        details.remove_children()

        # Plugin name
        details.mount(BoldPrimaryText(plugin_name))
        details.mount(Text(""))

        # Status
        if needs_attention:
            details.mount(Static("[bold]Status:[/bold] [yellow]Setup needed[/yellow]"))
            details.mount(DimText("Slack is configured for this repository, but your personal Slack account is not connected yet."))
        elif is_enabled:
            details.mount(Static("[bold]Status:[/bold] [green]Enabled[/green]"))
        else:
            details.mount(Static("[bold]Status:[/bold] [red]Disabled[/red]"))

        # Plugin metadata
        if plugin:
            if hasattr(plugin, '__doc__') and plugin.__doc__:
                details.mount(Text(""))  # Spacer
                details.mount(BoldText("Description:"))
                # Clean docstring: remove indentation from each line
                lines = plugin.__doc__.strip().split('\n')
                clean_lines = [line.strip() for line in lines if line.strip()]
                clean_desc = '\n'.join(clean_lines)
                details.mount(DimText(clean_desc))
                details.mount(Text(""))

            version = self.config.registry.get_plugin_version(plugin_name)
            details.mount(Static(f"[bold]Version:[/bold] {version}"))

            trust = self.config.registry.get_plugin_trust(plugin_name)
            if trust is not None:
                details.mount(Static(f"[bold]Trust:[/bold] {trust}"))

            findings = self.config.registry.get_security_findings(plugin_name)
            if findings:
                details.mount(Text(""))
                details.mount(Static(
                    f"[bold yellow]⚠ Security scan:[/bold yellow] this plugin's source "
                    f"touches secret machinery ({len(findings)} finding(s)):"
                ))
                for finding in findings[:5]:
                    details.mount(DimText(f"  {finding.file}:{finding.line} — {finding.detail}"))
                if len(findings) > 5:
                    details.mount(DimText(f"  … and {len(findings) - 5} more (see logs)"))

        # Check if plugin has configuration schema
        has_config = False
        if plugin and hasattr(plugin, 'get_config_schema'):
            try:
                schema = plugin.get_config_schema()
                if schema and schema.get('properties'):
                    has_config = True
            except Exception:
                pass

        details.mount(Text(""))  # Spacer
        if has_config:
            details.mount(DimText("✓ This plugin supports configuration"))
        else:
            details.mount(DimText("✗ This plugin has no configuration options"))

        # Show current configuration if enabled
        if is_enabled and self.config.config and self.config.config.plugins:
            plugin_cfg = self.config.config.plugins.get(plugin_name)
            if plugin_cfg and plugin_cfg.config:
                details.mount(Text(""))  # Spacer
                details.mount(BoldText("Current Configuration:"))
                for key, value in plugin_cfg.config.items():
                    # Don't show secrets
                    if any(secret in key.lower() for secret in ['token', 'password', 'secret', 'api_key']):
                        details.mount(DimText(f"  {key}: ••••••••"))
                    elif isinstance(value, list):
                        label = key.replace("_", " ").title()
                        if not value:
                            details.mount(DimText(f"  {label}: Not set"))
                        else:
                            details.mount(DimText(f"  {label}:"))
                            for item in value:
                                details.mount(DimText(f"    - {item}"))
                    elif isinstance(value, dict):
                        label = key.replace("_", " ").title()
                        if not value:
                            details.mount(DimText(f"  {label}: Not set"))
                        else:
                            details.mount(DimText(f"  {label}:"))
                            for nested_key, nested_value in value.items():
                                details.mount(
                                    DimText(
                                        f"    {nested_key.replace('_', ' ').title()}: {nested_value}"
                                    )
                                )
                    else:
                        label = key.replace("_", " ").title()
                        rendered = value if value not in (None, "") else "Not set"
                        details.mount(DimText(f"  {label}: {rendered}"))

        active_rec = self._build_stable_record(plugin_name)
        is_community_plugin = self._is_community_plugin(plugin_name)
        active_channel = self.config.get_plugin_source_channel(plugin_name)
        active_path = self.config.get_plugin_source_path(plugin_name)
        switch_value = self._get_source_switch_value(active_channel, active_path, active_rec)
        source_label = "Development Source" if active_channel == PluginChannel.DEV_LOCAL else PluginChannel.STABLE
        if active_rec:
            details.mount(Text(""))
            details.mount(BoldText("Source:"))
            if is_enabled and is_community_plugin and switch_value:
                details.mount(
                    Horizontal(
                        DimText("  Active:"),
                        self._build_source_switch(switch_value),
                        classes="source-switch-row",
                    )
                )
                self._source_switch_plugin = plugin_name
            else:
                details.mount(DimText(f"  Active: {source_label}"))
            if active_channel == PluginChannel.DEV_LOCAL and active_path:
                details.mount(DimText(f"  Path: {active_path}"))
            elif active_rec.repo_url:
                details.mount(DimText(f"  Repo: {active_rec.repo_url}"))
                if active_rec.requested_ref:
                    details.mount(DimText(f"  {active_rec.requested_ref} → {active_rec.resolved_commit}"))
            if active_rec.installed_at:
                details.mount(DimText(f"  Installed: {active_rec.installed_at[:10]}"))
        elif active_channel == PluginChannel.DEV_LOCAL and active_path:
            details.mount(Text(""))
            details.mount(BoldText("Source:"))
            if is_enabled and is_community_plugin and switch_value:
                details.mount(
                    Horizontal(
                        DimText("  Active:"),
                        self._build_source_switch(switch_value),
                        classes="source-switch-row",
                    )
                )
                self._source_switch_plugin = plugin_name
            else:
                details.mount(DimText("  Active: Development Source"))
            details.mount(DimText(f"  Path: {active_path}"))
        else:
            self._source_switch_plugin = None

        details.mount(Text(""))  # Spacer
        details.mount(BoldText("Actions:"))
        action_verb = "disable" if is_enabled else "enable"
        details.mount(DimText(f"  Press e to {action_verb} this plugin"))
        details.mount(DimText("  Press c to configure this plugin"))
        if active_channel == PluginChannel.DEV_LOCAL:
            details.mount(DimText("  Press u to remove the development source"))
        elif active_rec:
            details.mount(DimText("  Press u to remove this plugin from the current project"))
        if is_community_plugin:
            details.mount(DimText("  Press d to configure a local development path"))

        # Buttons
        details.mount(Text(""))  # Spacer
        buttons = [
            Button("Enable/Disable", variant="default", id="toggle-button"),
            Button("Configure", variant="primary", id="configure-button"),
        ]
        if is_community_plugin:
            buttons.append(Button("Set Dev Path", variant="default", id="set-dev-path-button"))
        if active_channel == PluginChannel.STABLE and active_rec:
            buttons.append(Button("Update", variant="warning", id="update-button"))
        if active_channel == PluginChannel.DEV_LOCAL or active_rec:
            buttons.append(Button("Remove", variant="error", id="uninstall-button"))
        details.mount(Horizontal(*buttons, classes="button-container"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "toggle-button":
            self.action_toggle_plugin()
        elif event.button.id == "configure-button":
            self.action_configure_plugin()
        elif event.button.id in ("install-plugin-button", "install-plugin-button-details"):
            self.action_install_plugin()
        elif event.button.id == "remove-plugin-button-details":
            self.action_remove_plugin_from_project()
        elif event.button.id == "update-button":
            self.action_update_plugin()
        elif event.button.id == "uninstall-button":
            self.action_uninstall_plugin()
        elif event.button.id == "set-dev-path-button":
            self.action_set_dev_source()

    def on_segmented_switch_changed(self, event: SegmentedSwitch.Changed) -> None:
        """Handle source switch changes."""
        if not self._source_switch_plugin or self._source_switch_plugin != self.selected_plugin:
            return

        try:
            active_path = self.config.get_plugin_source_path(self.selected_plugin)

            if event.value == PluginChannel.STABLE:
                if not active_path:
                    self.app.notify(
                        "No local development path is configured for this plugin.",
                        severity="warning",
                    )
                    return
                self.config.set_global_plugin_source(
                    self.selected_plugin,
                    PluginChannel.STABLE,
                    str(active_path),
                )
            elif event.value == PluginChannel.DEV_LOCAL:
                if not active_path:
                    self.app.notify(
                        "No local development path is configured for this plugin.",
                        severity="warning",
                    )
                    return

                self.config.set_global_plugin_source(
                    self.selected_plugin,
                    PluginChannel.DEV_LOCAL,
                    str(active_path),
                )

            self.config.load()
            self.installed_plugins = self.config.registry.list_installed()
            self._show_plugin_details(self.selected_plugin)
            self.app.notify(
                f"Plugin source for '{self.selected_plugin}' changed to "
                f"{'Development Source' if event.value == PluginChannel.DEV_LOCAL else PluginChannel.STABLE}.",
                severity="information",
            )
        except Exception as e:
            logger.exception("plugin_source_switch_failed", plugin=self.selected_plugin, value=event.value)
            self.app.notify(f"Failed to change plugin source: {e}", severity="error")

    def _build_source_switch(self, value: str) -> SegmentedSwitch:
        """Build the reusable source switch widget."""
        return SegmentedSwitch(
            options=[
                SegmentedSwitchOption(value=PluginChannel.STABLE, label="Stable"),
                SegmentedSwitchOption(value=PluginChannel.DEV_LOCAL, label="Develop"),
            ],
            value=value,
            boxed=False,
        )

    def _get_source_switch_value(self, active_channel: str, active_path, active_record: CommunityPluginRecord | None) -> str | None:
        """Return the switch value when source switching should be available."""
        if active_path:
            if active_channel == PluginChannel.DEV_LOCAL:
                return PluginChannel.DEV_LOCAL
            if active_record:
                return PluginChannel.STABLE
        return None

    def _is_community_plugin(self, plugin_name: str) -> bool:
        """Return whether the plugin is managed as a community plugin."""
        return self._build_stable_record(plugin_name) is not None or self.config.get_plugin_source_path(plugin_name) is not None

    def _build_stable_record(self, plugin_name: str) -> CommunityPluginRecord | None:
        """Build a synthetic stable record from the shared project config."""
        repo_url = self.config.get_project_plugin_repo_url(plugin_name)
        resolved_commit = self.config.get_project_plugin_resolved_commit(plugin_name)
        if not repo_url or not resolved_commit:
            return None

        requested_ref = self.config.get_project_plugin_requested_ref(plugin_name) or resolved_commit
        return CommunityPluginRecord(
            repo_url=repo_url,
            package_name=plugin_name,
            titan_plugin_name=plugin_name,
            installed_at="",
            channel=PluginChannel.STABLE,
            dev_local_path=None,
            requested_ref=requested_ref,
            resolved_commit=resolved_commit,
        )

    def action_toggle_plugin(self) -> None:
        """Toggle enable/disable state of selected plugin."""
        if not self.selected_plugin:
            self.app.notify("Please select a plugin", severity="warning")
            return

        try:
           
            project_cfg_path = self.config.project_config_path
            if not project_cfg_path or not project_cfg_path.exists():
                self.app.notify("No project configuration found", severity="error")
                return

            # Load current config
            with open(project_cfg_path, "rb") as f:
                project_cfg_dict = tomli.load(f)

            # Ensure plugin entry exists
            plugins_table = project_cfg_dict.setdefault("plugins", {})
            plugin_table = plugins_table.setdefault(self.selected_plugin, {})

            # Toggle enabled state
            current_state = plugin_table.get("enabled", True)
            new_state = not current_state
            plugin_table["enabled"] = new_state

            # Save config
            with open(project_cfg_path, "wb") as f:
                tomli_w.dump(project_cfg_dict, f)

            # Reload config
            self.config.load()

            # Refresh display
            self._load_plugins()

            action = "enabled" if new_state else "disabled"
            logger.info("plugin_toggled", plugin=self.selected_plugin, enabled=new_state)
            self.app.notify(f"Plugin '{self.selected_plugin}' {action}", severity="information")

        except Exception as e:
            logger.exception("plugin_toggle_failed", plugin=self.selected_plugin)
            self.app.notify(f"Failed to toggle plugin: {e}", severity="error")

    def action_configure_plugin(self) -> None:
        """Open configuration wizard for selected plugin."""
        if not self.selected_plugin:
            self.app.notify("Please select a plugin", severity="warning")
            return

        if not plugin_has_config_ui(self.config, self.selected_plugin):
            self.app.notify("This plugin has no configuration options", severity="warning")
            return

        # Open configuration wizard
        logger.info("plugin_configure_opened", plugin=self.selected_plugin)

        def on_wizard_close(result):
            if result:
                logger.info("plugin_configure_saved", plugin=self.selected_plugin)
                self.config.load()
                self._load_plugins()
            else:
                logger.info("plugin_configure_cancelled", plugin=self.selected_plugin)

        self.app.push_screen(
            resolve_plugin_config_screen(self.config, self.selected_plugin),
            on_wizard_close,
        )

    def action_install_plugin(self) -> None:
        """Open the community plugin install wizard."""
        def on_install_done(result):
            if result:
                self._load_plugins()
                self.app.notify("Plugin installed and loaded!", severity="information")

        self.app.push_screen(InstallPluginScreen(self.config), on_install_done)

    def action_set_dev_source(self) -> None:
        """Configure a local development path for the selected plugin."""
        if not self.selected_plugin:
            self.app.notify("Please select a plugin", severity="warning")
            return

        if not self._is_community_plugin(self.selected_plugin):
            self.app.notify(
                "Development source is only available for community plugins.",
                severity="warning",
            )
            return

        current_path = self.config.get_plugin_source_path(self.selected_plugin)

        self.app.push_screen(
            DevSourcePathModal(
                plugin_name=self.selected_plugin,
                initial_value=str(current_path) if current_path else "",
            ),
            self._handle_dev_source_selected,
        )

    def _handle_dev_source_selected(self, path_value: str | None) -> None:
        """Persist a validated development source path for the selected plugin."""
        if not path_value or not self.selected_plugin:
            return

        repo_path = Path(path_value).expanduser().resolve()
        error = get_local_plugin_validation_error(repo_path, self.selected_plugin)
        if error:
            logger.warning(
                "plugin_dev_source_validation_failed",
                plugin=self.selected_plugin,
                path=str(repo_path),
                error=error,
            )
            self.app.notify(error, severity="error")
            return

        self.config.set_global_plugin_source(
            self.selected_plugin,
            PluginChannel.STABLE,
            str(repo_path),
        )
        self.config.load()
        self.installed_plugins = self.config.registry.list_installed()
        self._show_plugin_details(self.selected_plugin)
        logger.info(
            "plugin_dev_source_configured",
            plugin=self.selected_plugin,
            path=str(repo_path),
        )
        self.app.notify(
            f"Development path configured for '{self.selected_plugin}'.",
            severity="information",
        )

    def action_remove_plugin_from_project(self) -> None:
        """Remove the selected missing plugin from the current project's config."""
        plugin_name = self.selected_missing_plugin
        if not plugin_name:
            self.app.notify("Please select a missing plugin", severity="warning")
            return

        try:
            self._remove_plugin_from_project(plugin_name)
            self.selected_missing_plugin = None
            self.config.load()
            self._load_plugins()
            self.app.notify(f"Plugin '{plugin_name}' removed from this project.", severity="information")
        except Exception as e:
            logger.exception("plugin_remove_from_project_failed", plugin=plugin_name)
            self.app.notify(f"Failed to remove plugin from project: {e}", severity="error")

    def action_update_plugin(self) -> None:
        """Check for and apply an update to the selected stable community plugin."""
        if not self.selected_plugin:
            self.app.notify("Please select a plugin", severity="warning")
            return

        active_record = self._build_stable_record(self.selected_plugin)
        if not active_record or active_record.channel != PluginChannel.STABLE:
            self.app.notify("Only plugins currently using the stable source can be updated", severity="warning")
            return

        record = self._build_stable_record(self.selected_plugin)
        if not record:
            self.app.notify("Only stable community plugins can be updated", severity="warning")
            return

        self.run_worker(self._run_update(record), exclusive=True)

    async def _run_update(self, record: CommunityPluginRecord) -> None:
        """Check for the latest version and install it if available."""
        self.app.notify(f"Checking for updates to '{record.titan_plugin_name}'…", severity="information", timeout=30)

        token = await asyncio.to_thread(get_github_token)
        latest = await asyncio.to_thread(check_for_update, record, token)

        if not latest:
            self.app.notify(
                f"'{record.titan_plugin_name}' is already up to date ({record.requested_ref}).",
                severity="information",
            )
            return

        self.app.notify(
            f"Updating '{record.titan_plugin_name}' {record.requested_ref} → {latest}…",
            severity="information",
            timeout=60,
        )

        token = await asyncio.to_thread(get_github_token)
        from titan_cli.core.plugins.community_sources import detect_host, resolve_ref_to_commit_sha
        host = detect_host(record.repo_url)
        resolved_sha, sha_error = await asyncio.to_thread(
            resolve_ref_to_commit_sha, record.repo_url, latest, host, token
        )

        if sha_error or not resolved_sha:
            self.app.notify(
                f"Could not resolve '{latest}' to a commit SHA: {sha_error}",
                severity="error",
            )
            return

        try:
            await asyncio.to_thread(
                self._update_project_stable_source,
                record.titan_plugin_name,
                record.repo_url,
                latest,
                resolved_sha,
            )
        except Exception as e:
            logger.error("plugin_update_failed", plugin=record.titan_plugin_name, error=str(e))
            self.app.notify(
                f"Failed to update '{record.titan_plugin_name}': {e}",
                severity="error",
            )
            return

        self.config.load()
        self._load_plugins()
        logger.info("plugin_updated", plugin=record.titan_plugin_name, version=latest)
        self.app.notify(
            f"'{record.titan_plugin_name}' updated to {latest}.",
            severity="information",
        )

    def action_uninstall_plugin(self) -> None:
        """Remove the selected project-pinned community plugin or dev override."""
        if not self.selected_plugin:
            self.app.notify("Please select a plugin", severity="warning")
            return

        if self.config.get_plugin_source_channel(self.selected_plugin) == PluginChannel.DEV_LOCAL:
            self.config.clear_global_plugin_source(self.selected_plugin)
            self.config.load()
            self.installed_plugins = self.config.registry.list_installed()
            self._show_plugin_details(self.selected_plugin)
            self.app.notify(
                f"Development source removed for '{self.selected_plugin}'",
                severity="information",
            )
            return

        record = self._build_stable_record(self.selected_plugin)
        if not record:
            self.app.notify("Only community plugins can be removed", severity="warning")
            return

        self.run_worker(self._run_uninstall(record.titan_plugin_name), exclusive=True)

    async def _run_uninstall(self, titan_plugin_name: str) -> None:
        """Remove a stable community plugin from the current project config."""
        logger.info("plugin_uninstall_started", plugin=titan_plugin_name, channel=PluginChannel.STABLE)
        self.app.notify(f"Removing '{titan_plugin_name}' from this project…", severity="information", timeout=30)

        try:
            await asyncio.to_thread(self._remove_plugin_from_project, titan_plugin_name)
        except Exception as e:
            logger.error("plugin_uninstall_failed", plugin=titan_plugin_name, error=str(e))
            self.app.notify(
                f"Failed to remove '{titan_plugin_name}' from this project: {e}",
                severity="error",
            )
            return

        logger.info("plugin_uninstalled", plugin=titan_plugin_name, channel=PluginChannel.STABLE)
        self.config.load()
        self._load_plugins()
        self.app.notify(f"Plugin '{titan_plugin_name}' removed from this project.", severity="information")

    def _update_project_stable_source(
        self,
        plugin_name: str,
        repo_url: str,
        requested_ref: str,
        resolved_commit: str,
    ) -> None:
        """Update the shared stable pin for a project community plugin."""
        project_cfg_path = self.config.project_config_path
        if not project_cfg_path or not project_cfg_path.exists():
            raise FileNotFoundError("No project configuration found")

        with open(project_cfg_path, "rb") as f:
            project_cfg_dict = tomli.load(f)

        plugin_table = project_cfg_dict.setdefault("plugins", {}).setdefault(plugin_name, {})
        plugin_table["enabled"] = True
        source_table = plugin_table.setdefault("source", {})
        source_table["channel"] = PluginChannel.STABLE
        source_table["repo_url"] = repo_url
        source_table["requested_ref"] = requested_ref
        source_table["resolved_commit"] = resolved_commit

        with open(project_cfg_path, "wb") as f:
            tomli_w.dump(project_cfg_dict, f)

    def _remove_plugin_from_project_config(self, plugin_name: str) -> None:
        """Remove a plugin block from the current project's config."""
        project_cfg_path = self.config.project_config_path
        if not project_cfg_path or not project_cfg_path.exists():
            raise FileNotFoundError("No project configuration found")

        with open(project_cfg_path, "rb") as f:
            project_cfg_dict = tomli.load(f)

        plugins_table = project_cfg_dict.get("plugins")
        if not plugins_table or plugin_name not in plugins_table:
            raise KeyError(f"Plugin '{plugin_name}' is not configured in this project")

        plugins_table.pop(plugin_name, None)

        with open(project_cfg_path, "wb") as f:
            tomli_w.dump(project_cfg_dict, f)

    def _remove_plugin_from_project(self, plugin_name: str) -> None:
        """Remove a plugin from the project and clear any local source override."""
        self._remove_plugin_from_project_config(plugin_name)
        self.config.clear_global_plugin_source(plugin_name)
