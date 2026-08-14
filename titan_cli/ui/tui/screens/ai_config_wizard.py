"""
AI Configuration Wizard Screen

Step-by-step wizard for configuring AI connections with visual progress tracking.
"""

from textual.app import ComposeResult
from textual.widgets import Static, OptionList, Input
from textual.widgets.option_list import Option
from textual.containers import Container, Horizontal, VerticalScroll
from textual.binding import Binding

from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import Text, DimText, BoldText, Button, Panel
from .base import BaseScreen


class StepIndicator(Static):
    """Widget showing a single step with status indicator."""

    def __init__(self, step_number: int, title: str, status: str = "pending"):
        self.step_number = step_number
        self.title = title
        self.status = status
        super().__init__()

    def render(self) -> str:
        """Render the step with appropriate icon."""
        if self.status == "completed":
            icon = Icons.SUCCESS
            style = "dim"
        elif self.status == "in_progress":
            icon = Icons.RUNNING
            style = "bold cyan"
        else:  # pending
            icon = Icons.PENDING
            style = "dim"

        return f"[{style}]{icon} {self.step_number}. {self.title}[/{style}]"


class AIConfigWizardScreen(BaseScreen):
    """
    Wizard screen for AI connection configuration.
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    CSS = """
    AIConfigWizardScreen {
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

    #steps-content {
        height: auto;
    }

    #button-container {
        height: auto;
        padding: 1 2;
        background: $surface-lighten-1;
        border-top: solid $primary;
        align: right middle;
    }

    #type-options-list, #source-options-list {
        height: auto;
        margin-top: 1;
        margin-bottom: 2;
        border: solid $accent;
    }

    #type-options-list > .option-list--option,
    #source-options-list > .option-list--option {
        padding: 1;
    }

    #type-options-list > .option-list--option-highlighted,
    #source-options-list > .option-list--option-highlighted {
        padding: 1;
    }

    Input {
        width: 100%;
        margin-top: 1;
        border: solid $accent;
    }

    Input:focus {
        border: solid $primary;
    }
    """

    @staticmethod
    def _build_connection_id(connection_name: str) -> str:
        """Build a stable TOML-safe connection id."""
        import re

        connection_id = re.sub(r"[^a-z0-9]+", "-", connection_name.lower()).strip("-")
        if not connection_id:
            raise ValueError("Connection name must contain letters or numbers.")
        return connection_id

    def __init__(self, config):
        super().__init__(
            config,
            title=f"{Icons.AI_CONFIG} Configure AI Connection",
            show_back=True,
            show_status_bar=False
        )
        self.current_step = 0
        self.wizard_data = {}

        # Define all wizard steps
        # Note: API Key comes before Model to support dynamic model fetching
        self.steps = [
            {"id": "type", "title": "Connection Type"},
            {"id": "source", "title": "Select Source"},
            {"id": "base_url", "title": "Base URL"},
            {"id": "api_key", "title": "API Key"},
            {"id": "model", "title": "Select Model"},
            {"id": "name", "title": "Connection Name"},
            {"id": "advanced", "title": "Advanced Options"},
            {"id": "review", "title": "Review & Save"},
        ]

    def compose_content(self) -> ComposeResult:
        """Compose the wizard screen with two panels."""
        with Container(id="wizard-container"):
            with Horizontal():
                # Left panel: Steps
                left_panel = VerticalScroll(id="steps-panel")
                left_panel.border_title = "Configuration Steps"
                with left_panel:
                    with Container(id="steps-content"):
                        for i, step in enumerate(self.steps, 1):
                            status = "in_progress" if i == 1 else "pending"
                            yield StepIndicator(i, step["title"], status=status)

                # Right panel: Content
                right_panel = Container(id="content-panel")
                right_panel.border_title = "Step Configuration"
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
        """Load the first step when mounted."""
        self.load_step(0)

    def load_step(self, step_index: int) -> None:
        """Load content for the given step."""
        self.current_step = step_index
        step = self.steps[step_index]

        # Update step indicators
        for i, indicator in enumerate(self.query(StepIndicator)):
            if i < step_index:
                indicator.status = "completed"
            elif i == step_index:
                indicator.status = "in_progress"
            else:
                indicator.status = "pending"
            indicator.refresh()

        # Update buttons
        back_button = self.query_one("#back-button", Button)
        back_button.disabled = (step_index == 0)

        # Change Next button to Save on last step
        next_button = self.query_one("#next-button", Button)
        if step_index == len(self.steps) - 1:
            next_button.label = "Save"
        else:
            next_button.label = "Next"

        # Load step content
        content_title = self.query_one("#content-title", Static)
        content_body = self.query_one("#content-body", Container)

        if step["id"] == "type":
            self.load_type_step(content_title, content_body)
        elif step["id"] == "base_url":
            self.load_base_url_step(content_title, content_body)
        elif step["id"] == "source":
            self.load_source_step(content_title, content_body)
        elif step["id"] == "api_key":
            self.load_api_key_step(content_title, content_body)
        elif step["id"] == "model":
            self.load_model_step(content_title, content_body)
        elif step["id"] == "name":
            self.load_name_step(content_title, content_body)
        elif step["id"] == "advanced":
            self.load_advanced_step(content_title, content_body)
        elif step["id"] == "review":
            self.load_review_step(content_title, content_body)

    def load_type_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load connection type step."""
        title_widget.update("Select Connection Type")

        # Clear previous content
        body_widget.remove_children()

        # Add description
        description = Static(
            "Choose how Titan should connect to AI:\n\n"
            "• LLM Gateway: One endpoint exposing multiple models\n"
            "• Direct Provider: Connect directly to one vendor API"
        )
        body_widget.mount(description)

        # Add options
        options = OptionList(
            Option("LLM Gateway", id="gateway"),
            Option("Direct Provider", id="direct_provider"),
            id="type-options-list"
        )
        body_widget.mount(options)

        # Focus the options list
        self.call_after_refresh(lambda: options.focus())

    def load_base_url_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load base URL step for gateway connections."""
        title_widget.update("Base URL Configuration")
        body_widget.remove_children()

        description = Text(
            "Enter the base URL for your AI gateway.\n\n"
            "This should be an OpenAI-compatible gateway endpoint such as LiteLLM."
        )
        body_widget.mount(description)

        examples = DimText(
            "\nExamples:\n"
            "  • http://localhost:4000\n"
            "  • https://llm.yourcompany.com/v1\n"
            "  • http://vllm-server:8000/v1\n"
            "  • https://gateway.internal/api/v1"
        )
        body_widget.mount(examples)

        # Add input field with default value
        default_url = self.wizard_data.get("base_url", "https://")
        input_widget = Input(
            value=default_url,
            placeholder="Enter base URL...",
            id="base-url-input"
        )
        input_widget.styles.margin = (2, 0, 0, 0)
        body_widget.mount(input_widget)

        # Focus the input
        self.call_after_refresh(lambda: input_widget.focus())

    def load_source_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load source selection step."""
        title_widget.update("Select Source")
        body_widget.remove_children()

        description = Text(
            "Choose the direct provider.\n\n"
            "Select the vendor API you want to connect to directly."
        )
        body_widget.mount(description)

        options = OptionList(
            Option("Anthropic (Claude)", id="anthropic"),
            Option("OpenAI", id="openai"),
            Option("Google (Gemini)", id="gemini"),
            id="source-options-list",
        )
        body_widget.mount(options)

        # Focus the options list
        self.call_after_refresh(lambda: options.focus())

    def load_api_key_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load API Key step."""
        title_widget.update("Enter API Key")
        body_widget.remove_children()

        source = self.wizard_data.get("source", "")
        connection_type = self.wizard_data.get("connection_type", "")
        source_name = (
            "LiteLLM / Gateway"
            if connection_type == "gateway"
            else "Anthropic"
            if source == "anthropic"
            else "OpenAI"
            if source == "openai"
            else "Google"
            if source == "gemini"
            else "AI"
        )

        if connection_type == "gateway":
            description = Text(
                "Enter your API key (optional).\n\n"
                "Some gateways don't require authentication.\n"
                "Leave blank if your gateway does not require an API key.\n"
                "This key will be securely stored in your system's keyring."
            )
        else:
            description = Text(
                f"Enter your {source_name} API key.\n\n"
                f"This key will be securely stored in your system's keyring."
            )
        body_widget.mount(description)

        if connection_type == "gateway":
            info = DimText(
                "\nAPI Key Details:\n"
                "  • Check your gateway documentation for authentication requirements\n"
                "  • LiteLLM gateways may or may not require API keys\n"
                "  • Leave blank if not required"
            )
        else:
            info = DimText(
                "\nWhere to get your API key:\n"
                "  • Anthropic: https://console.anthropic.com/settings/keys\n"
                "  • OpenAI: https://platform.openai.com/api-keys\n"
                "  • Google: https://aistudio.google.com/app/apikey"
            )
        body_widget.mount(info)

        # Add input field (password type to hide the key)
        default_key = self.wizard_data.get("api_key", "")
        input_widget = Input(
            value=default_key,
            placeholder="Enter API key...",
            password=True,
            id="api-key-input"
        )
        input_widget.styles.margin = (2, 0, 0, 0)
        body_widget.mount(input_widget)

        # Focus the input
        self.call_after_refresh(lambda: input_widget.focus())

    def load_model_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load Model Selection step."""
        title_widget.update("Select Model")
        body_widget.remove_children()

        connection_type = self.wizard_data.get("connection_type", "")
        base_url = self.wizard_data.get("base_url", "")
        source = self.wizard_data.get("source", "")

        if connection_type == "gateway":
            self._load_gateway_model_selection(body_widget, source, base_url)
        else:
            self._load_manual_model_input(body_widget, source)

    def _load_gateway_model_selection(
        self, body_widget: Container, source: str, base_url: str
    ) -> None:
        """Load model selection for a gateway with dynamic API fetch."""
        from titan_cli.ai.llm_tools import fetch_available_models
        from titan_cli.ui.tui.widgets import StyledOptionList, StyledOption

        # Get API key (already entered in previous step)
        api_key = self.wizard_data.get("api_key", "")

        # Add description
        body_widget.mount(Text("Fetching available models from gateway..."))
        body_widget.mount(DimText(""))

        # Show loading indicator
        loading_widget = DimText("Loading models...")
        body_widget.mount(loading_widget)

        try:
            # Fetch models from API with source filter
            models = fetch_available_models(
                base_url=base_url, api_key=api_key, provider_filter=source
            )

            # Clear loading message
            body_widget.remove_children()

            if not models:
                body_widget.mount(
                    Panel(
                        f"No models found for source '{source}' in this gateway.\n\n"
                        "You can enter a model name manually.",
                        panel_type="info",
                    )
                )
                self._load_manual_model_input(body_widget, source)
                return

            # Add header with better spacing
            source_name = (
                "Gateway"
                if source == "openai_compatible"
                else "Claude"
                if source == "anthropic"
                else "OpenAI"
                if source == "openai"
                else "Gemini"
            )
            body_widget.mount(BoldText(f"Available {source_name} models from gateway"))
            body_widget.mount(DimText("Select a model from the list below."))
            body_widget.mount(Text(""))  # Empty line for spacing

            styled_options = [
                StyledOption(
                    id=model.id,
                    title=model.id,
                    description="",
                )
                for model in models
            ]

            option_list = StyledOptionList(*styled_options, id="gateway-model-list")
            body_widget.mount(option_list)

            self.call_after_refresh(lambda: option_list.focus())

        except Exception as e:
            body_widget.remove_children()

            body_widget.mount(
                Panel(
                    f"Could not fetch models from gateway API.\n\n"
                    f"Error: {str(e)}\n\n"
                    "You can enter a model name manually below.",
                    panel_type="warning",
                )
            )
            body_widget.mount(Text(""))  # Spacing
            self._load_manual_model_input(body_widget, source)

    def _load_manual_model_input(self, body_widget: Container, source: str) -> None:
        """Load manual model input."""
        # Add description
        description = Text(
            "Enter the model to use.\n\n"
            "You can choose from popular models or enter a model name manually."
        )
        body_widget.mount(description)

        # Show popular models based on source
        if source == "anthropic":
            models_info = DimText(
                "\nPopular Claude models:\n"
                "  • claude-3-5-sonnet-20241022\n"
                "  • claude-3-opus-20240229\n"
                "  • claude-3-sonnet-20240229\n"
                "  • claude-3-haiku-20240307\n"
                "  • claude-3-5-haiku-20241022"
            )
        elif source == "openai":
            models_info = DimText(
                "\nPopular OpenAI models:\n"
                "  • gpt-5\n"
                "  • gpt-5-mini\n"
                "  • gpt-4.1"
            )
        elif source == "gemini":
            models_info = DimText(
                "\nPopular Gemini models:\n"
                "  • gemini-1.5-pro\n"
                "  • gemini-1.5-flash\n"
                "  • gemini-pro"
            )
        else:
            models_info = DimText("\nEnter the model name exposed by your gateway.")

        body_widget.mount(models_info)

        # Add input field with default model
        from titan_cli.ai.constants import get_default_model

        default_model = self.wizard_data.get(
            "model", get_default_model(source) if source else ""
        )

        input_widget = Input(
            value=default_model, placeholder="Enter model name...", id="model-input"
        )
        input_widget.styles.margin = (2, 0, 0, 0)
        body_widget.mount(input_widget)

        # Focus the input
        self.call_after_refresh(lambda: input_widget.focus())

    def load_name_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load connection name step."""
        title_widget.update("Connection Name")
        body_widget.remove_children()

        # Add description
        description = Text(
            "Name this AI connection.\n\n"
            "This helps you identify this configuration when you have multiple connections."
        )
        body_widget.mount(description)

        # Generate default name based on connection type and source
        connection_type = self.wizard_data.get("connection_type", "")
        source = self.wizard_data.get("source", "")

        connection_type_label = (
            "LLM Gateway" if connection_type == "gateway" else "Direct Provider"
        )
        source_name = (
            "LiteLLM Gateway"
            if connection_type == "gateway"
            else "Anthropic"
            if source == "anthropic"
            else "OpenAI"
            if source == "openai"
            else "Google"
            if source == "gemini"
            else "AI"
        )

        default_name = self.wizard_data.get(
            "connection_name", f"{connection_type_label} {source_name}"
        )

        # Add example
        example = DimText(
            f"\nExamples:\n"
            f"  • {connection_type_label} {source_name}\n"
            f"  • My {source_name} Account\n"
            f"  • Work Gateway\n"
            f"  • OpenAI Personal"
        )
        body_widget.mount(example)

        # Add input field
        input_widget = Input(
            value=default_name,
            placeholder="Enter connection name...",
            id="name-input"
        )
        input_widget.styles.margin = (2, 0, 0, 0)
        body_widget.mount(input_widget)

        # Focus the input
        self.call_after_refresh(lambda: input_widget.focus())

    def load_advanced_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load Advanced Options step."""
        title_widget.update("Advanced Options")
        body_widget.remove_children()

        # Add description
        description = Text(
            "Configure advanced AI parameters (optional).\n\n"
            "These settings control the AI's behavior. You can use the defaults or customize them."
        )
        body_widget.mount(description)

        # Get source to show correct temperature range
        source = self.wizard_data.get("source", "")
        max_temp = "1.0" if source == "anthropic" else "2.0"

        # Temperature input
        temp_label = Text(f"\nTemperature (0.0 - {max_temp}):")
        temp_label.styles.margin = (2, 0, 0, 0)
        body_widget.mount(temp_label)

        temp_info = DimText(
            "Controls randomness. Lower = more focused, higher = more creative.\n"
            "Default: 0.7"
        )
        body_widget.mount(temp_info)

        default_temp = str(self.wizard_data.get("temperature", "0.7"))
        temp_input = Input(
            value=default_temp,
            placeholder="0.7",
            id="temperature-input"
        )
        temp_input.styles.margin = (1, 0, 0, 0)
        body_widget.mount(temp_input)

        # Max tokens input
        tokens_label = Text("\nMax Tokens:")
        tokens_label.styles.margin = (2, 0, 0, 0)
        body_widget.mount(tokens_label)

        tokens_info = DimText(
            "Maximum length of AI responses.\n"
            "Default: 4096"
        )
        body_widget.mount(tokens_info)

        default_tokens = str(self.wizard_data.get("max_tokens", "4096"))
        tokens_input = Input(
            value=default_tokens,
            placeholder="4096",
            id="max-tokens-input"
        )
        tokens_input.styles.margin = (1, 0, 0, 0)
        body_widget.mount(tokens_input)

        # Focus the temperature input
        self.call_after_refresh(lambda: temp_input.focus())

    def load_review_step(self, title_widget: Static, body_widget: Container) -> None:
        """Load Review & Save step."""
        title_widget.update("Review Configuration")
        body_widget.remove_children()

        # Add description
        description = Text(
            "Review your configuration before saving.\n\n"
            "Please verify all settings are correct."
        )
        body_widget.mount(description)

        # Build configuration summary
        connection_type = self.wizard_data.get("connection_type", "")
        base_url = self.wizard_data.get("base_url", "")
        source = self.wizard_data.get("source", "")
        model = self.wizard_data.get("model", "")
        connection_name = self.wizard_data.get("connection_name", "")
        temperature = self.wizard_data.get("temperature", 0.7)
        max_tokens = self.wizard_data.get("max_tokens", 4096)

        source_label = (
            "LiteLLM / OpenAI-compatible Gateway"
            if connection_type == "gateway"
            else "Anthropic"
            if source == "anthropic"
            else "OpenAI"
            if source == "openai"
            else "Google"
            if source == "gemini"
            else source
        )
        connection_type_label = (
            "LLM Gateway" if connection_type == "gateway" else "Direct Provider"
        )

        # Create summary text
        summary = Text("\n")
        summary.styles.margin = (2, 0, 0, 0)
        body_widget.mount(summary)

        # Configuration details
        from titan_cli.ui.tui.widgets import BoldText

        body_widget.mount(BoldText("Connection Type:"))
        body_widget.mount(DimText(f"  {connection_type_label}"))
        body_widget.mount(Text(""))

        if base_url:
            body_widget.mount(BoldText("Base URL:"))
            body_widget.mount(DimText(f"  {base_url}"))
            body_widget.mount(Text(""))

        body_widget.mount(BoldText("Source:"))
        body_widget.mount(DimText(f"  {source_label}"))
        body_widget.mount(Text(""))

        body_widget.mount(BoldText("Model:"))
        body_widget.mount(DimText(f"  {model}"))
        body_widget.mount(Text(""))

        body_widget.mount(BoldText("Connection Name:"))
        body_widget.mount(DimText(f"  {connection_name}"))
        body_widget.mount(Text(""))

        body_widget.mount(BoldText("Temperature:"))
        body_widget.mount(DimText(f"  {temperature}"))
        body_widget.mount(Text(""))

        body_widget.mount(BoldText("Max Tokens:"))
        body_widget.mount(DimText(f"  {max_tokens}"))
        body_widget.mount(Text(""))

        body_widget.mount(BoldText("API Key:"))
        body_widget.mount(DimText("  ••••••••••••••••••••"))
        body_widget.mount(Text(""))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection in lists - auto-advance to next step."""
        # Save the selection and move to next step
        self.handle_next()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields - auto-advance to next step."""
        self.handle_next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "next-button":
            self.handle_next()
        elif event.button.id == "back-button":
            self.handle_back()
        elif event.button.id == "cancel-button":
            self.action_back()

    def handle_next(self) -> None:
        """Move to next step or save configuration."""
        # Validate and save current step data
        if not self.validate_and_save_step():
            return

        # If on last step, save configuration
        if self.current_step == len(self.steps) - 1:
            self.save_configuration()
            return

        # Move to next step
        if self.current_step < len(self.steps) - 1:
            next_step = self.current_step + 1

            # Skip Source for gateway because there is only one gateway backend today.
            if self.steps[next_step]["id"] == "source":
                connection_type = self.wizard_data.get("connection_type", "")
                if connection_type == "gateway":
                    self.wizard_data["source"] = "openai_compatible"
                    next_step += 1

            # Skip Base URL unless this is a gateway connection
            if self.steps[next_step]["id"] == "base_url":
                connection_type = self.wizard_data.get("connection_type", "")
                if connection_type != "gateway":
                    next_step += 1

            self.load_step(next_step)

    def validate_and_save_step(self) -> bool:
        """Validate and save data from current step."""
        step = self.steps[self.current_step]

        if step["id"] == "type":
            # Get selected connection type
            try:
                options_list = self.query_one("#type-options-list", OptionList)
                if options_list.highlighted is None:
                    self.app.notify(
                        "Please select a connection type", severity="warning"
                    )
                    return False

                selected_option = options_list.get_option_at_index(options_list.highlighted)
                self.wizard_data["connection_type"] = selected_option.id
                return True
            except Exception as e:
                self.app.notify(f"Error selecting type: {e}", severity="error")
                return False

        elif step["id"] == "base_url":
            # Get base URL from input
            try:
                input_widget = self.query_one("#base-url-input", Input)
                base_url = input_widget.value.strip()

                # Validate URL
                if not base_url:
                    self.app.notify("Please enter a base URL", severity="warning")
                    return False

                if not base_url.startswith(("http://", "https://")):
                    self.app.notify("Base URL must start with http:// or https://", severity="warning")
                    return False

                self.wizard_data["base_url"] = base_url
                return True
            except Exception:
                self.app.notify("Please enter a valid base URL", severity="error")
                return False

        elif step["id"] == "source":
            # Get selected source
            try:
                options_list = self.query_one("#source-options-list", OptionList)
                if options_list.highlighted is None:
                    self.app.notify("Please select a source", severity="warning")
                    return False

                selected_option = options_list.get_option_at_index(options_list.highlighted)
                self.wizard_data["source"] = selected_option.id
                return True
            except Exception:
                self.app.notify("Please select a source", severity="error")
                return False

        elif step["id"] == "api_key":
            # Get API key from input
            try:
                input_widget = self.query_one("#api-key-input", Input)
                api_key = input_widget.value.strip()

                connection_type = self.wizard_data.get("connection_type", "")
                if not api_key:
                    if connection_type == "gateway":
                        self.wizard_data["api_key"] = ""
                        return True
                    else:
                        self.app.notify("Please enter an API key", severity="warning")
                        return False

                # Basic validation: should be alphanumeric with possible hyphens/underscores
                if len(api_key) < 10:
                    self.app.notify("API key seems too short", severity="warning")
                    return False

                self.wizard_data["api_key"] = api_key
                return True
            except Exception:
                self.app.notify("Please enter a valid API key", severity="error")
                return False

        elif step["id"] == "model":
            # Check if using LLM Tools selection or manual input
            try:
                # Try to get from option list first (LLM Tools)
                from titan_cli.ui.tui.widgets import StyledOptionList

                option_list = self.query_one("#gateway-model-list", StyledOptionList)
                model_id = option_list.get_selected_id()

                if not model_id:
                    self.app.notify("Please select a model", severity="warning")
                    return False

                self.wizard_data["model"] = model_id
                return True

            except Exception:
                # Fallback to manual input
                try:
                    input_widget = self.query_one("#model-input", Input)
                    model = input_widget.value.strip()

                    if not model:
                        self.app.notify("Please enter a model name", severity="warning")
                        return False

                    self.wizard_data["model"] = model
                    return True
                except Exception:
                    self.app.notify("Could not get model selection", severity="error")
                    return False

        elif step["id"] == "name":
            # Get connection name from input
            try:
                input_widget = self.query_one("#name-input", Input)
                connection_name = input_widget.value.strip()

                if not connection_name:
                    self.app.notify(
                        "Please enter a connection name", severity="warning"
                    )
                    return False

                self.wizard_data["connection_name"] = connection_name
                return True
            except Exception:
                self.app.notify(
                    "Please enter a valid connection name", severity="error"
                )
                return False

        elif step["id"] == "advanced":
            # Get temperature and max_tokens
            try:
                temp_input = self.query_one("#temperature-input", Input)
                tokens_input = self.query_one("#max-tokens-input", Input)

                source = self.wizard_data.get("source", "")
                max_temp = 1.0 if source == "anthropic" else 2.0

                # Validate temperature
                try:
                    temperature = float(temp_input.value.strip())
                    if temperature < 0.0 or temperature > max_temp:
                        self.app.notify(f"Temperature must be between 0.0 and {max_temp}", severity="warning")
                        return False
                except ValueError:
                    self.app.notify("Temperature must be a number", severity="warning")
                    return False

                # Validate max_tokens
                try:
                    max_tokens = int(tokens_input.value.strip())
                    if max_tokens < 1:
                        self.app.notify("Max tokens must be at least 1", severity="warning")
                        return False
                except ValueError:
                    self.app.notify("Max tokens must be a number", severity="warning")
                    return False

                self.wizard_data["temperature"] = temperature
                self.wizard_data["max_tokens"] = max_tokens
                return True
            except Exception:
                self.app.notify("Please enter valid advanced options", severity="error")
                return False

        # TODO: Add validation for review step
        return True

    def handle_back(self) -> None:
        """Move to previous step."""
        if self.current_step > 0:
            prev_step = self.current_step - 1

            # Skip Source on backward nav for gateway because there is only one backend.
            if self.steps[prev_step]["id"] == "source":
                connection_type = self.wizard_data.get("connection_type", "")
                if connection_type == "gateway":
                    prev_step -= 1

            # Skip Base URL on backward nav unless this is a gateway
            if self.steps[prev_step]["id"] == "base_url":
                connection_type = self.wizard_data.get("connection_type", "")
                if connection_type != "gateway":
                    prev_step -= 1

            self.load_step(prev_step)

    def save_configuration(self) -> None:
        """Save the AI connection configuration."""
        from titan_cli.core.security import create_broker_factory
        from titan_cli.core.logging import get_logger
        from titan_cli.core.models import (
            AIConnectionType,
            AIGatewayBackend,
            AIDirectProvider,
        )

        logger = get_logger(__name__)
        logger.debug("ai_wizard_save_started")

        try:
            connection_name = self.wizard_data.get("connection_name", "")
            connection_id = self._build_connection_id(connection_name)

            ai_cfg = self.config.get_ai_connections_config()
            if connection_id in ai_cfg["connections"]:
                self.app.notify(
                    f"Connection ID '{connection_id}' already exists",
                    severity="error",
                )
                return

            selected_source = self.wizard_data.get("source")
            connection_type = self.wizard_data.get("connection_type")

            connection_cfg = {
                "name": connection_name,
                "default_model": self.wizard_data.get("model"),
                "temperature": self.wizard_data.get("temperature", 0.7),
                "max_tokens": self.wizard_data.get("max_tokens", 4096),
            }

            if self.wizard_data.get("base_url"):
                connection_cfg["base_url"] = self.wizard_data.get("base_url")

            if connection_type == "gateway":
                connection_cfg["connection_type"] = AIConnectionType.GATEWAY.value
                connection_cfg["gateway_backend"] = (
                    AIGatewayBackend.OPENAI_COMPATIBLE.value
                )
            else:
                connection_cfg["connection_type"] = AIConnectionType.DIRECT_PROVIDER.value
                connection_cfg["provider"] = AIDirectProvider(selected_source).value

            self.config.upsert_ai_connection(connection_id, connection_cfg)
            logger.info("ai_config_saved", connection=connection_name)

            # Save API key to secrets (if provided)
            broker = create_broker_factory().for_plugin("core")
            api_key = self.wizard_data.get("api_key")
            if api_key:  # Only save if API key is not empty
                broker.store(f"{connection_id}_api_key", api_key)
                logger.debug("api_key_saved", connection_id=connection_id)
            else:
                logger.debug(
                    "api_key_skipped", connection_id=connection_id, reason="empty_key"
                )

            # Show success message
            self.app.notify(
                f"AI connection '{connection_name}' configured successfully!",
                severity="information",
            )

            # Close wizard and trigger callback
            logger.debug("ai_wizard_completed", connection=connection_name)
            self.dismiss(result=True)

        except Exception as e:
            logger.exception(
                "ai_wizard_save_failed",
                connection=self.wizard_data.get("connection_name"),
            )
            self.app.notify(f"Failed to save configuration: {e}", severity="error")

    def action_back(self) -> None:
        """Cancel and go back."""
        self.dismiss(result=False)
