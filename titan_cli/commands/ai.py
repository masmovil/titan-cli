# titan_cli/commands/ai.py
import typer
import tomli
import tomli_w

from ..core.config import TitanConfig
from ..core.secrets import SecretManager
from ..ui.components.typography import TextRenderer
from ..ui.components.spacer import SpacerRenderer
from ..ui.views.prompts import PromptsRenderer
from ..ui.views.menu_components.dynamic_menu import DynamicMenu
from ..ai.client import PROVIDER_CLASSES
from ..ai.oauth_helper import OAuthHelper
from ..ai.constants import get_default_model, get_provider_name
from ..ai.models import AIRequest, AIMessage
from ..messages import msg
from ..utils.claude_integration import ClaudeCodeLauncher # New import
from typing import Optional # New import

ai_app = typer.Typer(name="ai", help="Configure and manage AI providers.")

@ai_app.command("chat")
def chat(prompt: Optional[str] = None):
    """Launch Claude Code for AI assistance."""
    text = TextRenderer()

    if not ClaudeCodeLauncher.is_available():
        text.error(msg.Code.NOT_INSTALLED)
        text.body(msg.Code.INSTALL_INSTRUCTIONS)
        raise typer.Exit(1)

    text.info(msg.Code.LAUNCHING)
    if prompt:
        text.body(msg.Code.INITIAL_PROMPT.format(prompt=prompt))
    text.line()

    exit_code = ClaudeCodeLauncher.launch(prompt=prompt)

    text.line()
    text.success(msg.Code.RETURNED)

    if exit_code != 0:
        raise typer.Exit(exit_code)


def _select_model(provider: str, prompts: PromptsRenderer, text: TextRenderer) -> str:
    """
    Interactive model selection with free input and visual suggestions.

    Args:
        provider: Provider key (anthropic, openai, gemini)
        prompts: PromptsRenderer instance
        text: TextRenderer instance

    Returns:
        Selected model name
    """
    spacer = SpacerRenderer()

    text.subtitle(msg.AI.MODEL_SELECTION_TITLE.format(provider=get_provider_name(provider)))
    spacer.line()

    # Show popular models as reference (not exhaustive list)
    if provider == "anthropic":
        text.body(msg.AI.POPULAR_CLAUDE_MODELS_TITLE, style="dim")
        text.body(msg.AI.POPULAR_CLAUDE_SONNET_3_5, style="dim")
        text.body(msg.AI.POPULAR_CLAUDE_OPUS, style="dim")
        text.body(msg.AI.POPULAR_CLAUDE_HAIKU, style="dim")
        text.body(msg.AI.POPULAR_CLAUDE_HAIKU_3_5, style="dim")

    elif provider == "openai":
        text.body(msg.AI.POPULAR_OPENAI_MODELS_TITLE, style="dim")
        text.body(msg.AI.POPULAR_OPENAI_GPT4_TURBO, style="dim")
        text.body(msg.AI.POPULAR_OPENAI_GPT4, style="dim")
        text.body(msg.AI.POPULAR_OPENAI_GPT3_5_TURBO, style="dim")

    elif provider == "gemini":
        text.body(msg.AI.POPULAR_GEMINI_MODELS_TITLE, style="dim")
        text.body(msg.AI.POPULAR_GEMINI_1_5_PRO, style="dim")
        text.body(msg.AI.POPULAR_GEMINI_1_5_FLASH, style="dim")
        text.body(msg.AI.POPULAR_GEMINI_PRO, style="dim")

    spacer.line()
    text.body(msg.AI.MODEL_SELECTION_TIP, style="dim")
    spacer.line()

    # Free text input with sensible default
    default_model = get_default_model(provider)
    model = prompts.ask_text(
        msg.AI.MODEL_PROMPT,
        default=default_model
    )

    return model or default_model


def _test_ai_connection(provider: str, secrets: SecretManager, model: str = None, base_url: str = None):
    """
    Internal helper to test AI provider connection.

    Args:
        provider: Provider key
        secrets: SecretManager instance
        model: Optional model name to test (uses provider's model if None)
        base_url: Optional custom endpoint URL
    """
    text = TextRenderer()

    model_info = f" with model '{model}'" if model else ""
    endpoint_info = f" (custom endpoint)" if base_url else ""
    text.info(msg.AI.TESTING_CONNECTION.format(provider=provider, model_info=model_info, endpoint_info=endpoint_info))

    try:
        provider_class = PROVIDER_CLASSES.get(provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider}")

        # Get API key
        api_key = secrets.get(f"{provider}_api_key")

        # Special case for Gemini OAuth
        if provider == "gemini" and secrets.get("gemini_oauth_enabled"):
             api_key = "GCLOUD_OAUTH"

        if not api_key:
            raise ValueError(f"API key for {provider} not found.")

        # Instantiate provider with model and base_url
        kwargs = {"api_key": api_key}
        if model:
            kwargs["model"] = model
        if base_url:
            kwargs["base_url"] = base_url

        provider_instance = provider_class(**kwargs)

        # Generate a simple test response
        test_request = AIRequest(
            messages=[AIMessage(role="user", content="Say 'Hello!' if you can hear me")],
            max_tokens=50
        )
        response = provider_instance.generate(test_request)

        text.success(msg.AI.CONNECTION_SUCCESS)
        text.body(msg.AI.TEST_MODEL_INFO.format(model=response.model), style="dim")
        text.body(msg.AI.TEST_RESPONSE_INFO.format(content=response.content), style="dim")

    except Exception as e:
        text.error(msg.AI.CONNECTION_FAILED.format(error=e))
        return False

    return True

def configure_ai_interactive():
    """Interactive AI configuration workflow."""
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)
    secrets = SecretManager()

    text.title(msg.AI.CONFIG_TITLE)
    text.line()

    # Step 1: Select Provider
    provider_menu = DynamicMenu(title=msg.AI.PROVIDER_SELECT_TITLE, emoji=msg.EMOJI.INFO) # Changed emoji to INFO
    cat = provider_menu.add_category(msg.AI.PROVIDER_SELECT_CATEGORY)
    cat.add_item(msg.AI.ANTHROPIC_LABEL, msg.AI.ANTHROPIC_DESCRIPTION_MODEL.format(model="claude-3-opus-20240229"), "anthropic")
    cat.add_item(msg.AI.OPENAI_LABEL, msg.AI.OPENAI_DESCRIPTION_MODEL.format(model="gpt-4-turbo"), "openai")
    cat.add_item(msg.AI.GEMINI_LABEL, msg.AI.GEMINI_DESCRIPTION_MODEL.format(model="gemini-1.5-pro"), "gemini")

    provider_choice = prompts.ask_menu(provider_menu.to_menu())
    if not provider_choice:
        text.warning(msg.Secrets.AI_SETUP_CANCELLED)
        return

    provider = provider_choice.action
    text.line()

    # Step 2: Authentication
    auth_successful = False
    if provider == "gemini":
        text.info(msg.AI.GEMINI_OAUTH_INFO)
        use_oauth = prompts.ask_confirm(msg.AI.GEMINI_OAUTH_PROMPT, default=True)
        if use_oauth:
            helper = OAuthHelper()
            status = helper.check_gcloud_auth()
            if not status.available:
                text.error(msg.AI.GEMINI_OAUTH_NOT_AVAILABLE.format(error=status.error))
                text.body(helper.get_install_instructions())
                return
            if not status.authenticated:
                text.warning(msg.AI.GEMINI_OAUTH_NOT_AUTHENTICATED)
                if prompts.ask_confirm(msg.AI.GEMINI_OAUTH_RUN_LOGIN_PROMPT):
                    text.body(helper.get_auth_instructions())
                return # Exit if user doesn't want to authenticate now
            
            secrets.set("gemini_oauth_enabled", "true", scope="user")
            text.success(msg.AI.GEMINI_OAUTH_CONFIGURED_SUCCESS)
            auth_successful = True
        else: # User chose not to use OAuth, prompt for API key
             api_key = secrets.prompt_and_set(
                key="gemini_api_key",
                prompt_text=msg.AI.API_KEY_PROMPT.format(provider="Gemini"), # Gemini title is hardcoded here, need to check if provider.title() is what we want
                scope="user"
            )
             if api_key:
                 secrets.delete("gemini_oauth_enabled", scope="user") # Ensure OAuth is not enabled
                 auth_successful = True
    else: # API Key flow for Anthropic/OpenAI
        key_name = f"{provider}_api_key"
        if secrets.get(key_name):
            text.info(msg.AI.API_KEY_ALREADY_CONFIGURED.format(provider=provider))
            if not prompts.ask_confirm(msg.AI.API_KEY_REPLACE_PROMPT):
                text.warning(msg.Secrets.AI_SETUP_CANCELLED)
                return
        
        api_key = secrets.prompt_and_set(key=key_name, prompt_text=msg.AI.API_KEY_PROMPT.format(provider=provider.title()), scope="user")
        if api_key:
            auth_successful = True
    
    if not auth_successful:
        text.warning(msg.Secrets.AI_SETUP_CANCELLED)
        return

    text.line()

    # Step 3: Custom Endpoint (Optional - for enterprise/corporate deployments)
    base_url = None
    if prompts.ask_confirm(
        msg.AI.CUSTOM_ENDPOINT_PROMPT,
        default=False
    ):
        spacer = SpacerRenderer()
        spacer.line()
        text.info(msg.AI.CUSTOM_ENDPOINT_INFO_TITLE)
        text.body(msg.AI.CUSTOM_ENDPOINT_INFO_PROXY, style="dim")
        text.body(msg.AI.CUSTOM_ENDPOINT_INFO_BEDROCK, style="dim")
        text.body(msg.AI.CUSTOM_ENDPOINT_INFO_AZURE, style="dim")
        text.body(msg.AI.CUSTOM_ENDPOINT_INFO_SELF_HOSTED, style="dim")
        spacer.line()

        if provider == "anthropic":
            text.body(msg.AI.CUSTOM_ENDPOINT_EXAMPLE_ANTHROPIC, style="dim")
        elif provider == "openai":
            text.body(msg.AI.CUSTOM_ENDPOINT_EXAMPLE_OPENAI, style="dim")

        spacer.line()
        base_url = prompts.ask_text(
            msg.AI.CUSTOM_ENDPOINT_URL_PROMPT,
            default=""
        )

        if base_url:
            text.success(msg.AI.CUSTOM_ENDPOINT_SUCCESS.format(base_url=base_url))
        else:
            text.info(msg.AI.CUSTOM_ENDPOINT_USING_STANDARD)

        text.line()

    # Step 4: Model Selection
    model = _select_model(provider, prompts, text)
    text.line()

    # Step 5: Advanced Options
    temperature = None
    max_tokens = None
    if prompts.ask_confirm(msg.AI.ADVANCED_OPTIONS_PROMPT, default=False):
        text.line()
        temperature = prompts.ask_float(
            msg.AI.TEMPERATURE_PROMPT,
            default=0.7,
            min_value=0.0,
            max_value=2.0
        )
        max_tokens = prompts.ask_int(
            msg.AI.MAX_TOKENS_PROMPT,
            default=4096,
            min_value=1
        )
        text.line()

    # Step 6: Save to global config
    global_config_path = TitanConfig.GLOBAL_CONFIG
    global_config = {}
    if global_config_path.exists():
        with open(global_config_path, "rb") as f:
            global_config = tomli.load(f)

    if "ai" not in global_config:
        global_config["ai"] = {}
    global_config["ai"]["provider"] = provider
    global_config["ai"]["model"] = model

    # Save advanced options if provided
    if temperature is not None:
        global_config["ai"]["temperature"] = temperature
    if max_tokens is not None:
        global_config["ai"]["max_tokens"] = max_tokens

    # Save base_url if provided
    if base_url:
        global_config["ai"]["base_url"] = base_url
    elif "base_url" in global_config.get("ai", {}):
        # Remove base_url if user didn't provide one (using standard endpoint)
        del global_config["ai"]["base_url"]

    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config, f)

    text.success(msg.AI.CONFIG_SUCCESS_TITLE)
    text.body(msg.AI.CONFIG_SUCCESS_PROVIDER.format(provider=get_provider_name(provider)), style="dim")
    text.body(msg.AI.CONFIG_SUCCESS_MODEL.format(model=model), style="dim")
    if base_url:
        text.body(msg.AI.CONFIG_SUCCESS_ENDPOINT.format(base_url=base_url), style="dim")
    if temperature is not None:
        text.body(msg.AI.CONFIG_SUCCESS_TEMPERATURE.format(temperature=temperature), style="dim")
    if max_tokens is not None:
        text.body(msg.AI.CONFIG_SUCCESS_MAX_TOKENS.format(max_tokens=max_tokens), style="dim")
    text.line()

    # Step 7: Test connection (optional)
    if prompts.ask_confirm(msg.AI.TEST_CONNECTION_PROMPT, default=True):
        test_success = _test_ai_connection(provider, secrets, model, base_url)
        if not test_success:
            text.line()
            text.warning(msg.AI.CONNECTION_TEST_FAILED_PROMPT)
            if prompts.ask_confirm(msg.AI.RECONFIGURE_PROMPT, default=False):
                configure_ai_interactive()  # Recursive call to reconfigure

@ai_app.command("configure")
def configure():
    """Configure your AI provider interactively."""
    configure_ai_interactive()

@ai_app.command("test")
def test():
    """Test the connection to the configured AI provider."""
    config = TitanConfig()
    secrets = SecretManager()

    if not config.config.ai:
        typer.echo(msg.AI.PROVIDER_NOT_CONFIGURED)
        raise typer.Exit(1)

    provider = config.config.ai.provider
    model = config.config.ai.model if config.config.ai.model else None

    base_url = config.config.ai.base_url

    _test_ai_connection(provider, secrets, model, base_url)
