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
from ..ai.client import PROVIDER_CLASSES, AIClient
from ..ai.constants import get_default_model, get_provider_name
from ..ai.models import AIRequest, AIMessage
from ..ai.exceptions import AIConfigurationError
from ..core.models import AIConfig, AIProviderConfig # Added AIProviderConfig import
from ..messages import msg
from ..utils.claude_integration import ClaudeCodeLauncher
from typing import Optional

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

@ai_app.command("list")
def list_providers():
    """List configured AI providers."""
    config = TitanConfig()
    text = TextRenderer()

    if not config.config.ai or not config.config.ai.providers:
        text.warning(msg.AI.PROVIDER_NOT_CONFIGURED)
        text.body(msg.AI.AI_SEE_AVAILABLE_PROVIDERS)
        return

    text.title(msg.AI.AI_CONFIG_PROVIDER_TITLE)
    text.line()

    default_id = config.config.ai.default

    for provider_id, provider_cfg in config.config.ai.providers.items():
        is_default = "⭐" if provider_id == default_id else "  "

        text.body(f"{is_default} {provider_cfg.name}", style="bold")
        text.body(msg.AI.AI_PROVIDER_ID.format(id=provider_id), style="dim")
        text.body(msg.AI.AI_PROVIDER_TYPE.format(type=provider_cfg.type), style="dim")
        text.body(msg.AI.AI_PROVIDER_NAME_MODEL.format(provider_name=get_provider_name(provider_cfg.provider), model=provider_cfg.model), style="dim")
        if provider_cfg.base_url:
            text.body(msg.AI.AI_PROVIDER_ENDPOINT.format(base_url=provider_cfg.base_url), style="dim")
        text.line()


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


def _test_ai_connection_by_id(provider_id: str, secrets: SecretManager, ai_config: AIConfig, provider_cfg: AIProviderConfig):
    """
    Internal helper to test AI provider connection by provider ID.
    Args:
        provider_id: ID of the provider to test.
        secrets: SecretManager instance.
        ai_config: The full AIConfig object, potentially containing other providers.
        provider_cfg: The specific AIProviderConfig object for this provider.
    """
    text = TextRenderer()

    # Create a temporary AIConfig to use for the AIClient, ensuring it has the full context
    # but with the specific provider_cfg potentially just configured.
    test_ai_config = AIConfig(default=ai_config.default, providers={pid: pcfg for pid, pcfg in ai_config.providers.items()})
    test_ai_config.providers[provider_id] = provider_cfg # Ensure the specific provider_cfg is the one being tested.

    try:
        # Initialize AIClient with the potentially modified test_ai_config and the specific provider_id
        ai_client = AIClient(test_ai_config, secrets, provider_id=provider_id)

        model_info = f" with model '{provider_cfg.model}'" if provider_cfg.model else ""
        endpoint_info = f" (custom endpoint)" if provider_cfg.base_url else ""
        text.info(msg.AI.TESTING_CONNECTION.format(provider=get_provider_name(provider_cfg.provider), model_info=model_info, endpoint_info=endpoint_info))

        # Generate a simple test response
        response = ai_client.generate(
            messages=[AIMessage(role="user", content="Say 'Hello!' if you can hear me")],
            max_tokens=200
        )

        text.success(msg.AI.CONNECTION_SUCCESS)
        text.body(msg.AI.TEST_MODEL_INFO.format(model=response.model), style="dim")
        text.body(msg.AI.TEST_RESPONSE_INFO.format(content=response.content), style="dim")

    except AIConfigurationError as e:
        text.error(msg.AI.CONNECTION_FAILED.format(error=e))
        text.body(msg.AI.AI_DETAILS.format(error=e), style="dim")
        return False
    except Exception as e:
        text.error(msg.AI.CONNECTION_FAILED.format(error=e))
        return False

    return True

def configure_ai_interactive():
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)
    secrets = SecretManager()

    text.title(msg.AI.AI_CONFIG_PROVIDER_TITLE)
    text.line()

    # Paso 1: Tipo de configuración
    type_menu = DynamicMenu(title=msg.AI.AI_CONFIG_TYPE_TITLE)
    cat = type_menu.add_category(msg.AI.AI_CONFIG_TYPE_SELECT)
    cat.add_item(msg.AI.AI_CONFIG_TYPE_CORPORATE_LABEL, msg.AI.AI_CONFIG_TYPE_CORPORATE_DESCRIPTION, "corporate")
    cat.add_item(msg.AI.AI_CONFIG_TYPE_INDIVIDUAL_LABEL, msg.AI.AI_CONFIG_TYPE_INDIVIDUAL_DESCRIPTION, "individual")

    config_type_choice = prompts.ask_menu(type_menu.to_menu())
    if not config_type_choice:
        text.warning(msg.AI.AI_CONFIG_CANCELLED)
        return

    config_type = config_type_choice.action
    text.line()

    # Paso 2: Base URL (solo para corporativa)
    base_url = None
    if config_type == "corporate":
        text.info(msg.AI.AI_CONFIG_CORPORATE_INFO)
        text.body(msg.AI.AI_CONFIG_CORPORATE_BASE_URL_INFO, style="dim")
        text.body(msg.AI.AI_CONFIG_CORPORATE_BASE_URL_EXAMPLE, style="dim")
        text.line()

        base_url = prompts.ask_text(msg.AI.AI_CONFIG_CORPORATE_BASE_URL_PROMPT, default="https://api.your-company.com/llm") # Using generic example
        text.line()

    # Paso 3: Seleccionar provider
    provider_menu = DynamicMenu(title=msg.AI.AI_PROVIDER_SELECT_TITLE)
    cat = provider_menu.add_category(msg.AI.AI_PROVIDER_SELECT_CATEGORY)
    cat.add_item(msg.AI.ANTHROPIC_LABEL, msg.AI.AI_ANTHROPIC_DESCRIPTION, "anthropic")
    cat.add_item(msg.AI.OPENAI_LABEL, msg.AI.AI_OPENAI_DESCRIPTION, "openai")
    cat.add_item(msg.AI.AI_GEMINI_LABEL, msg.AI.AI_GEMINI_DESCRIPTION, "gemini")

    provider_choice = prompts.ask_menu(provider_menu.to_menu())
    if not provider_choice:
        text.warning(msg.AI.AI_CONFIG_CANCELLED)
        return

    provider = provider_choice.action
    text.line()

    # Paso 4: API Key
    text.info(msg.AI.AI_API_KEY_INFO.format(provider_name=get_provider_name(provider)))
    api_key = prompts.ask_text(msg.AI.AI_API_KEY_PROMPT.format(provider_name=get_provider_name(provider)), password=True)
    if not api_key:
        text.warning(msg.AI.AI_CONFIG_CANCELLED)
        return
    text.line()

    # Paso 5: Seleccionar modelo
    model = _select_model(provider, prompts, text)
    text.line()

    # Paso 6: Nombre del provider
    default_name = f"{msg.AI.AI_CONFIG_TYPE_CORPORATE_LABEL if config_type == 'corporate' else msg.AI.AI_CONFIG_TYPE_INDIVIDUAL_LABEL} {get_provider_name(provider)}"
    provider_name = prompts.ask_text(msg.AI.AI_PROVIDER_NAME_PROMPT, default=default_name)
    provider_id = provider_name.lower().replace(" ", "-")
    text.line()

    # Paso 7: Opciones avanzadas (opcional)
    temperature = 0.7
    max_tokens = 4096
    if prompts.ask_confirm(msg.AI.ADVANCED_OPTIONS_PROMPT, default=False):
        temperature = prompts.ask_float(msg.AI.TEMPERATURE_PROMPT, default=0.7, min_value=0.0, max_value=2.0)
        max_tokens = prompts.ask_int(msg.AI.MAX_TOKENS_PROMPT, default=4096, min_value=1)
        text.line()

    # Paso 8: Guardar configuración
    global_config_path = TitanConfig.GLOBAL_CONFIG
    global_config_data = {}
    if global_config_path.exists():
        with open(global_config_path, "rb") as f:
            global_config_data = tomli.load(f)

    # Inicializar estructura si no existe
    if "ai" not in global_config_data:
        global_config_data["ai"] = {}
    if "providers" not in global_config_data["ai"]:
        global_config_data["ai"]["providers"] = {}

    # Guardar provider
    provider_cfg_to_save = {
        "name": provider_name,
        "type": config_type,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if base_url:
        provider_cfg_to_save["base_url"] = base_url

    global_config_data["ai"]["providers"][provider_id] = provider_cfg_to_save

    # Marcar como default si es el primero o si el usuario lo confirma
    is_first = len(global_config_data["ai"]["providers"]) == 1
    if is_first or prompts.ask_confirm(msg.AI.AI_PROVIDER_MARK_DEFAULT_PROMPT, default=is_first):
        global_config_data["ai"]["default"] = provider_id
    elif "default" not in global_config_data["ai"]:
        # Si no hay default, usar el primero
        global_config_data["ai"]["default"] = list(global_config_data["ai"]["providers"].keys())[0]


    # Guardar en disco
    global_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # Guardar API key en secrets
    secrets.set(f"{provider_id}_api_key", api_key, scope="user")

    # Confirmación
    text.success(msg.AI.AI_PROVIDER_CONFIGURED_SUCCESS)
    text.body(msg.AI.AI_PROVIDER_NAME.format(name=provider_name), style="dim")
    text.body(msg.AI.AI_PROVIDER_ID.format(id=provider_id), style="dim")
    text.body(msg.AI.AI_PROVIDER_TYPE.format(type=config_type), style="dim")
    text.body(msg.AI.AI_PROVIDER_NAME_MODEL.format(provider_name=get_provider_name(provider), model=model), style="dim")
    if base_url:
        text.body(msg.AI.AI_PROVIDER_ENDPOINT.format(base_url=base_url), style="dim")
    text.line()

    # Test opcional
    if prompts.ask_confirm(msg.AI.TEST_CONNECTION_PROMPT, default=True):
        # Re-load config to get latest (including Pydantic validation)
        # This is crucial for passing a validated AIConfig and AIProviderConfig to the test function
        latest_config = TitanConfig()
        test_provider_cfg = latest_config.config.ai.providers[provider_id]
        _test_ai_connection_by_id(provider_id, secrets, latest_config.config.ai, test_provider_cfg)

@ai_app.command("configure")
def configure():
    """Configure your AI provider interactively."""
    configure_ai_interactive()

@ai_app.command("test")
def test(provider_id: Optional[str] = typer.Argument(None, help="ID of the provider to test.")):
    """Test the connection to the configured AI provider."""
    config = TitanConfig()
    secrets = SecretManager()
    text = TextRenderer()

    if not config.config.ai or not config.config.ai.providers:
        text.warning(msg.AI.PROVIDER_NOT_CONFIGURED)
        text.body(msg.AI.SEE_AVAILABLE_PROVIDERS)
        raise typer.Exit(1)

    if provider_id is None:
        provider_id = config.config.ai.default
        if not provider_id:
            text.error(msg.AI.AI_NO_DEFAULT_PROVIDER)
            raise typer.Exit(1)
        text.info(msg.AI.AI_TESTING_DEFAULT_PROVIDER.format(provider_id=provider_id))
        text.line()

    provider_cfg = config.config.ai.providers.get(provider_id)
    if not provider_cfg:
        text.error(msg.AI.AI_PROVIDER_NOT_FOUND_IN_CONFIG.format(provider_id=provider_id))
        text.body(msg.AI.SEE_AVAILABLE_PROVIDERS)
        raise typer.Exit(1)

    _test_ai_connection_by_id(provider_id, secrets, config.config.ai, provider_cfg)
