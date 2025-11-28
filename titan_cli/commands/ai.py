# titan_cli/commands/ai.py
import typer
import tomli
import tomli_w
from pathlib import Path

from ..core.config import TitanConfig
from ..core.secrets import SecretManager
from ..ui.components.typography import TextRenderer
from ..ui.views.prompts import PromptsRenderer
from ..ui.views.menu_components.dynamic_menu import DynamicMenu
from ..ai.client import AIClient
from ..ai.oauth_helper import OAuthHelper
from ..messages import msg
from ..ai.client import AIClient, PROVIDER_CLASSES
from ..ai.models import AIRequest, AIMessage


ai_app = typer.Typer(name="ai", help="Configure and manage AI providers.")

def _test_ai_connection(provider: str, secrets: SecretManager):
    """Internal helper to test AI provider connection."""
    text = TextRenderer()
    text.info(f"Testing {provider} connection...")

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

        # Instantiate provider and generate a simple response
        provider_instance = provider_class(api_key=api_key)
        test_request = AIRequest(messages=[AIMessage(role="user", content="Say 'Hello!' if you can hear me")])
        response = provider_instance.generate(test_request)

        text.success("✅ Connection successful!")
        text.body(f"Response: {response.content}", style="dim") # Access content from AIResponse

    except Exception as e:
        text.error(f"❌ Connection failed: {e}")

def configure_ai_interactive():
    """Interactive AI configuration workflow."""
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)
    secrets = SecretManager()
    config = TitanConfig() # To read existing global config

    text.title("🤖 Configure AI Provider")
    text.line()

    # Step 1: Select Provider
    provider_menu = DynamicMenu(title="Select AI Provider", emoji="🤖")
    cat = provider_menu.add_category("Providers")
    cat.add_item("Anthropic (Claude)", "Model: claude-3-opus-20240229", "anthropic")
    cat.add_item("OpenAI (GPT-4)", "Model: gpt-4-turbo", "openai")
    cat.add_item("Google (Gemini)", "Model: gemini-1.5-pro", "gemini")

    provider_choice = prompts.ask_menu(provider_menu.to_menu())
    if not provider_choice:
        text.warning(msg.Errors.OPERATION_CANCELLED)
        return

    provider = provider_choice.action
    text.line()

    # Step 2: Authentication
    auth_successful = False
    if provider == "gemini":
        text.info("Gemini can use OAuth via Google Cloud SDK.")
        use_oauth = prompts.ask_confirm("Use OAuth for Gemini authentication?", default=True)
        if use_oauth:
            helper = OAuthHelper()
            status = helper.check_gcloud_auth()
            if not status.available:
                text.error(f"Google Cloud SDK not found or not working: {status.error}")
                text.body(helper.get_install_instructions())
                return
            if not status.authenticated:
                text.warning("You are not authenticated with gcloud.")
                if prompts.ask_confirm("Run 'gcloud auth application-default login' now?"):
                    text.body(helper.get_auth_instructions())
                return # Exit if user doesn't want to authenticate now
            
            secrets.set("gemini_oauth_enabled", "true", scope="user")
            text.success("✅ Gemini configured to use Google Cloud OAuth.")
            auth_successful = True
        else: # User chose not to use OAuth, prompt for API key
             api_key = secrets.prompt_and_set(
                key="gemini_api_key",
                prompt_text="Enter your Gemini API key",
                scope="user"
            )
             if api_key:
                 secrets.delete("gemini_oauth_enabled", scope="user") # Ensure OAuth is not enabled
                 auth_successful = True
    else: # API Key flow for Anthropic/OpenAI
        key_name = f"{provider}_api_key"
        if secrets.get(key_name):
            text.info(f"API key already configured for {provider}.")
            if not prompts.ask_confirm("Do you want to replace the existing key?"):
                text.warning(msg.Errors.OPERATION_CANCELLED)
                return
        
        api_key = secrets.prompt_and_set(key=key_name, prompt_text=f"Enter your {provider.title()} API Key", scope="user")
        if api_key:
            auth_successful = True
    
    if not auth_successful:
        text.warning(msg.Errors.OPERATION_CANCELLED)
        return

    text.line()

    # Step 3: Save to global config (only if auth_successful is True)
    global_config_path = TitanConfig.GLOBAL_CONFIG
    global_config = {}
    if global_config_path.exists():
        with open(global_config_path, "rb") as f:
            global_config = tomli.load(f)
    
    if "ai" not in global_config:
        global_config["ai"] = {}
    global_config["ai"]["provider"] = provider

    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config, f)
    
    text.success(f"✅ Default AI provider set to: {provider}")
    text.line()

    # Step 4: Test connection (only if auth_successful is True)
    if prompts.ask_confirm("Test AI connection now?"):
        _test_ai_connection(provider, secrets)

@ai_app.command("configure")
def configure():
    """Configure your AI provider interactively."""
    configure_ai_interactive()

@ai_app.command("test")
def test():
    """Test the connection to the configured AI provider."""
    config = TitanConfig()
    secrets = SecretManager()

    provider = config.config.ai.provider if config.config.ai else None
    if not provider:
        typer.echo("❌ No AI provider configured. Run: titan ai configure")
        raise typer.Exit(1)

    _test_ai_connection(provider, secrets)
