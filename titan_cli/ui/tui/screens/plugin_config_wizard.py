"""
Plugin Configuration Wizard Screen

Generic wizard that adapts to any plugin's configuration schema.
Each plugin can have different configuration steps based on its schema.
"""

from textual.app import ComposeResult
from textual.widgets import Static, Input
from textual.containers import Container, Horizontal, VerticalScroll
from textual.binding import Binding

from titan_cli.ui.tui.widgets import Text, DimText, Button, BoldText, StepIndicator, StepStatus, WizardStep, PromptOptionList, OptionItem
from titan_cli.ui.tui.icons import Icons
from .base import BaseScreen
from titan_cli.core.logging import get_logger

logger = get_logger(__name__)


class PluginConfigWizardScreen(BaseScreen):
    """
    Generic wizard for configuring any plugin.

    Adapts its steps based on the plugin's configuration schema.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    PluginConfigWizardScreen {
        align: center middle;
    }

    #wizard-container {
        width: 100%;
        height: 1fr;
        background: $surface-lighten-1;
        padding: 0 2 1 2;
    }

    #steps-panel {
        width: 20%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #steps-content {
        padding: 1;
    }

    StepIndicator {
        height: auto;
        margin-bottom: 1;
    }

    #content-panel {
        width: 80%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
        layout: vertical;
    }

    #content-scroll {
        height: 1fr;
    }

    #content-area {
        padding: 1;
        height: auto;
    }

    #content-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 2;
        height: auto;
    }

    #content-body {
        height: auto;
        margin-bottom: 2;
    }

    #button-container {
        height: auto;
        padding: 1 2;
        background: $surface-lighten-1;
        border-top: solid $primary;
        align: right middle;
    }

    .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }

    Input {
        width: 100%;
        margin-bottom: 2;
        border: solid $accent;
    }

    Input:focus {
        border: solid $primary;
    }
    """

    def __init__(self, config, plugin_name: str):
        super().__init__(
            config,
            title=f"{Icons.SETTINGS} Configure {plugin_name}",
            show_back=False,
            show_status_bar=False
        )
        self.plugin_name = plugin_name
        self.current_step = 0
        self.config_data = {}
        self.steps = []
        self.schema = None
        self.properties = {}
        self.required_fields = []

    def compose_content(self) -> ComposeResult:
        """Compose the wizard screen with two panels."""
        with Container(id="wizard-container"):
            with Horizontal():
                # Left panel: Steps
                left_panel = VerticalScroll(id="steps-panel")
                left_panel.border_title = "Configuration Steps"
                with left_panel:
                    with Container(id="steps-content"):
                        # Steps will be added dynamically
                        pass

                # Right panel: Content
                right_panel = Container(id="content-panel")
                right_panel.border_title = "Configuration"
                with right_panel:
                    with VerticalScroll(id="content-scroll"):
                        with Container(id="content-area"):
                            yield Static("", id="content-title")
                            yield Container(id="content-body")

                    # Bottom buttons
                    with Horizontal(id="button-container"):
                        yield Button("Back", variant="default", id="back-button", disabled=True)
                        yield Button("Next", variant="primary", id="next-button")
                        yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self) -> None:
        """Load plugin schema and build steps."""
        # Get plugin instance directly from registry's internal dict
        logger.debug("plugin_config_wizard_mounted", plugin=self.plugin_name, available_plugins=list(self.config.registry._plugins.keys()))

        plugin = self.config.registry._plugins.get(self.plugin_name)

        if not plugin:
            available = list(self.config.registry._plugins.keys())
            logger.error("plugin_not_found", plugin=self.plugin_name, available=available)
            self.app.notify(f"Plugin '{self.plugin_name}' not found", severity="error")
            self.dismiss(result=False)
            return

        # Check if plugin has configuration schema
        if not hasattr(plugin, "get_config_schema"):
            logger.debug("plugin_no_config_schema", plugin=self.plugin_name)
            self.dismiss(result=True)
            return

        try:
            self.schema = plugin.get_config_schema()
            logger.debug("plugin_schema_loaded", plugin=self.plugin_name)
        except Exception as e:
            logger.exception("plugin_schema_load_failed", plugin=self.plugin_name)
            self.app.notify(f"Failed to get config schema: {e}", severity="error")
            self.dismiss(result=False)
            return

        self.properties = self.schema.get("properties", {})
        self.required_fields = self.schema.get("required", [])

        logger.debug("plugin_schema_parsed", plugin=self.plugin_name, properties=list(self.properties.keys()), required_fields=self.required_fields)

        if not self.properties:
            logger.debug("plugin_no_config_fields", plugin=self.plugin_name)
            self.dismiss(result=True)
            return

        # Build steps based on field types
        self._build_steps()
        self._render_step_indicators()
        self.load_step(0)

    def _build_steps(self):
        """Build wizard steps based on plugin configuration schema."""
        # Group fields by type/category
        # For now, we'll create one step per field for simplicity
        # In the future, plugins could define custom step grouping

        for field_name in self.properties.keys():
            self.steps.append({
                "id": field_name,
                "title": field_name.replace("_", " ").title(),
                "field": field_name
            })

        # Add review step
        self.steps.append({
            "id": "review",
            "title": "Review",
            "field": None
        })

    def _render_step_indicators(self):
        """Render step indicators in the left panel."""
        steps_content = self.query_one("#steps-content", Container)

        for i, step in enumerate(self.steps, 1):
            status = StepStatus.IN_PROGRESS if i == 1 else StepStatus.PENDING
            steps_content.mount(StepIndicator(i, WizardStep(id=step["id"], title=step["title"]), status=status))

    def load_step(self, step_index: int):
        """Load content for the given step."""
        self.current_step = step_index
        step = self.steps[step_index]

        # Update step indicators
        for i, indicator in enumerate(self.query(StepIndicator)):
            if i < step_index:
                indicator.status = StepStatus.COMPLETED
            elif i == step_index:
                indicator.status = StepStatus.IN_PROGRESS
            else:
                indicator.status = StepStatus.PENDING
            indicator.refresh()

        # Update buttons
        back_button = self.query_one("#back-button", Button)
        back_button.disabled = (step_index == 0)

        next_button = self.query_one("#next-button", Button)
        if step_index == len(self.steps) - 1:
            next_button.label = "Save"
        else:
            next_button.label = "Next"

        # Load step content
        if step["id"] == "review":
            self.load_review_step()
        else:
            self.load_field_step(step["field"])

    def load_field_step(self, field_name: str):
        """Load a configuration field step."""
        content_title = self.query_one("#content-title", Static)
        content_body = self.query_one("#content-body", Container)

        content_title.update(field_name.replace("_", " ").title())
        content_body.remove_children()

        field_schema = self.properties[field_name]
        description = field_schema.get("description", "")
        field_format = field_schema.get("format", "")
        default_value = field_schema.get("default")
        is_required = field_name in self.required_fields

        # Detect if secret
        is_secret = (
            "token" in field_name.lower() or
            "password" in field_name.lower() or
            "secret" in field_name.lower() or
            "api_key" in field_name.lower() or
            field_format == "password"
        )

        # Show description
        if description:
            desc_text = Text(f"{description}\n")
            content_body.mount(desc_text)

        # Show if required
        if is_required:
            req_text = BoldText("This field is required.")
            content_body.mount(req_text)
        else:
            opt_text = DimText("This field is optional.")
            content_body.mount(opt_text)

        # Check for existing value
        current_value = self.config_data.get(field_name)
        if current_value is None:
            current_value = default_value

        # For secrets, check keychain
        if is_secret:
            project_name = self.config.get_project_name()
            secret_key = f"{self.plugin_name}_{field_name}"
            keychain_key = f"{project_name}_{secret_key}" if project_name else secret_key
            broker = self.config.broker_factory.for_plugin(self.plugin_name)
            existing_secret = broker.exists(keychain_key) or broker.exists(secret_key)

            if existing_secret:
                info = DimText("\n\nAlready configured. Leave blank to keep existing value.")
                content_body.mount(info)

        # Enum field: render PromptOptionList instead of Input
        enum_values = field_schema.get("enum")
        if enum_values:
            options = [
                OptionItem(value=v, title=str(v).capitalize())
                for v in enum_values
            ]
            def on_enum_select(value, fn=field_name):
                self.config_data[fn] = value

            enum_widget = PromptOptionList(
                question=f"Select {field_name.replace('_', ' ')}",
                options=options,
                on_select=on_enum_select,
            )
            content_body.mount(enum_widget)
            return

        # Create input
        input_value = ""
        if not is_secret and current_value is not None:
            input_value = str(current_value)

        input_widget = Input(
            value=input_value,
            placeholder=f"Enter {field_name}...",
            password=is_secret,
            id=f"input-{field_name}"
        )
        input_widget.styles.margin = (2, 0, 0, 0)
        content_body.mount(input_widget)

        # Focus input
        self.call_after_refresh(lambda: input_widget.focus())

    def load_review_step(self):
        """Load review step showing all configuration."""
        content_title = self.query_one("#content-title", Static)
        content_body = self.query_one("#content-body", Container)

        content_title.update("Review Configuration")
        content_body.remove_children()

        desc = Text("Please review your configuration before saving.\n")
        content_body.mount(desc)

        # Show all configured values
        for field_name, value in self.config_data.items():
            is_secret = (
                "token" in field_name.lower() or
                "password" in field_name.lower() or
                "secret" in field_name.lower() or
                "api_key" in field_name.lower()
            )

            label = BoldText(f"\n{field_name.replace('_', ' ').title()}:")
            content_body.mount(label)

            if is_secret:
                value_text = DimText("  ••••••••••••")
            else:
                value_text = DimText(f"  {value}")
            content_body.mount(value_text)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        self.handle_next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "next-button":
            self.handle_next()
        elif event.button.id == "back-button":
            self.handle_back()
        elif event.button.id == "cancel-button":
            self.action_cancel()

    def handle_next(self) -> None:
        """Move to next step or save."""
        # Validate and save current step
        if not self.validate_and_save_step():
            return

        # If on last step, save configuration
        if self.current_step == len(self.steps) - 1:
            self.save_configuration()
            return

        # Move to next step
        if self.current_step < len(self.steps) - 1:
            self.load_step(self.current_step + 1)

    def validate_and_save_step(self) -> bool:
        """Validate and save current step data."""
        step = self.steps[self.current_step]

        if step["id"] == "review":
            # No validation needed
            return True

        # Get field input
        field_name = step["field"]
        field_schema = self.properties[field_name]
        is_required = field_name in self.required_fields

        try:
            # Enum field: value is stored via callback on selection, not via Input widget
            enum_values = field_schema.get("enum")
            if enum_values:
                value = self.config_data.get(field_name)
                if is_required and not value:
                    self.app.notify(f"Please select a value for {field_name}", severity="warning")
                    return False
                return True

            input_widget = self.query_one(f"#input-{field_name}", Input)
            value = input_widget.value.strip()

            # Check for existing secret
            is_secret = (
                "token" in field_name.lower() or
                "password" in field_name.lower() or
                "secret" in field_name.lower() or
                "api_key" in field_name.lower()
            )

            if is_secret:
                project_name = self.config.get_project_name()
                secret_key = f"{self.plugin_name}_{field_name}"
                keychain_key = f"{project_name}_{secret_key}" if project_name else secret_key
                broker = self.config.broker_factory.for_plugin(self.plugin_name)
                existing_secret = broker.exists(keychain_key) or broker.exists(secret_key)

                if not value and existing_secret:
                    # Keep existing
                    self.config_data[field_name] = {"_is_secret": True, "_existing": True}
                    return True
                elif not value and is_required:
                    self.app.notify(f"{field_name} is required", severity="warning")
                    return False
                elif value:
                    self.config_data[field_name] = {"_is_secret": True, "_value": value}
                    return True
                return True

            # Validate required
            if is_required and not value:
                self.app.notify(f"{field_name} is required", severity="warning")
                return False

            # Skip empty optional fields
            if not value:
                return True

            # Type conversion
            field_type = field_schema.get("type")
            if field_type == "integer":
                try:
                    value = int(value)
                except ValueError:
                    self.app.notify(f"{field_name} must be a number", severity="warning")
                    return False
            elif field_type == "boolean":
                value = value.lower() in ("true", "yes", "1")

            self.config_data[field_name] = value
            return True

        except Exception:
            self.app.notify("Please enter a value", severity="error")
            return False

    def handle_back(self) -> None:
        """Move to previous step."""
        if self.current_step > 0:
            self.load_step(self.current_step - 1)

    def save_configuration(self) -> None:
        """Save plugin configuration."""
        import tomli
        import tomli_w

        try:
            project_cfg_path = self.config.project_config_path
            global_cfg_path = self.config._global_config_path

            if not project_cfg_path:
                self.app.notify("No project config found", severity="error")
                return

            # Load existing configs
            project_cfg_dict = {}
            if project_cfg_path.exists():
                with open(project_cfg_path, "rb") as f:
                    project_cfg_dict = tomli.load(f)

            global_cfg_dict = {}
            if global_cfg_path.exists():
                with open(global_cfg_path, "rb") as f:
                    global_cfg_dict = tomli.load(f)

            # Prepare plugin tables
            project_plugins_table = project_cfg_dict.setdefault("plugins", {})
            project_plugin_table = project_plugins_table.setdefault(self.plugin_name, {})
            project_config_table = project_plugin_table.setdefault("config", {})

            global_plugins_table = global_cfg_dict.setdefault("plugins", {})
            global_plugin_table = global_plugins_table.setdefault(self.plugin_name, {})
            global_config_table = global_plugin_table.setdefault("config", {})

            # Get field metadata from schema
            field_scopes = {}
            if self.schema and "properties" in self.schema:
                for field_name, field_info in self.schema["properties"].items():
                    scope = field_info.get("config_scope", "project")  # Default to project
                    field_scopes[field_name] = scope

            # Separate secrets and config by scope
            secrets_to_save = {}
            global_config_values = {}
            project_config_values = {}

            for field_name, value in self.config_data.items():
                if isinstance(value, dict) and value.get("_is_secret"):
                    secret_key = f"{self.plugin_name}_{field_name}"
                    if value.get("_existing"):
                        # Keep existing secret: it is already stored under one
                        # of the keys the plugin's read cascade checks, so
                        # there is nothing to rewrite.
                        continue
                    secrets_to_save[secret_key] = value["_value"]
                else:
                    # Route to global or project based on field scope
                    scope = field_scopes.get(field_name, "project")
                    if scope == "global":
                        global_config_values[field_name] = value
                    else:
                        project_config_values[field_name] = value

            # Update configs
            project_config_table.update(project_config_values)
            global_config_table.update(global_config_values)

            # Write config files
            with open(project_cfg_path, "wb") as f:
                tomli_w.dump(project_cfg_dict, f)

            if global_config_values:  # Only write global if there are global values
                with open(global_cfg_path, "wb") as f:
                    tomli_w.dump(global_cfg_dict, f)

            # Save secrets
            project_name = self.config.get_project_name()
            broker = self.config.broker_factory.for_plugin(self.plugin_name)
            for secret_key, secret_value in secrets_to_save.items():
                # Clean up old secrets for this key to avoid conflicts
                # This prevents accumulation of stale tokens from previous configurations
                if self.plugin_name == "jira" and "api_token" in secret_key:
                    # Delete all possible old JIRA token variants
                    old_keys = [
                        secret_key,  # Generic: jira_api_token
                        f"{project_name}_{secret_key}" if project_name else None,  # Project-specific
                    ]
                    for old_key in old_keys:
                        if old_key:
                            try:
                                broker.delete(old_key)
                            except Exception:
                                pass  # Ignore errors if key doesn't exist

                # Save the new secret
                keychain_key = f"{project_name}_{secret_key}" if project_name else secret_key
                broker.store(keychain_key, secret_value)

            self.app.notify(f"Plugin '{self.plugin_name}' configured successfully!", severity="information")
            self.dismiss(result=True)

        except Exception as e:
            self.app.notify(f"Failed to save configuration: {e}", severity="error")

    def action_cancel(self) -> None:
        """Cancel configuration."""
        self.dismiss(result=False)
