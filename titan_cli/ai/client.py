"""
AI Client - Main facade for AI functionality
"""

from typing import Callable, List, Optional

from titan_cli.core.models import (
    AIConfig,
    AIConnectionType,
    AIDirectProvider,
    AIGatewayBackend,
)
from titan_cli.core.interrupt import run_interruptible
from .exceptions import AIConfigurationError
from .models import AIMessage, AIRequest, AIResponse
from .providers import (
    AIProvider,
    AnthropicProvider,
    GeminiProvider,
    LiteLLMProvider,
    OpenAIProvider,
)


def get_provider_classes() -> dict[str, type[AIProvider]]:
    """Return the direct-provider class registry."""
    return {
        AIDirectProvider.ANTHROPIC.value: AnthropicProvider,
        AIDirectProvider.GEMINI.value: GeminiProvider,
        AIDirectProvider.OPENAI.value: OpenAIProvider,
    }


def get_gateway_classes() -> dict[str, type[AIProvider]]:
    """Return the gateway-provider class registry."""
    return {
        AIGatewayBackend.OPENAI_COMPATIBLE.value: LiteLLMProvider,
    }

class AIClient:
    """
    Main client for AI functionality.

    This facade simplifies AI usage by:
    - Reading configuration from AIConfig.
    - Delegating provider construction (and API-key handling) to the
      injected provider factory.
    - Instantiating the correct AI source adapter.
    - Providing a simple `generate()` and `chat()` interface.
    """

    def __init__(
        self,
        ai_config: AIConfig,
        provider_factory: Callable[[str, "object"], "AIProvider"],
        connection_id: Optional[str] = None,
    ):
        """
        Initialize AI client.

        Args:
            ai_config: The AI configuration.
            provider_factory: Builds the authenticated provider for
                `(connection_id, connection_cfg)` — normally
                `titan_cli.core.security.create_ai_provider`, which
                dereferences the API key inside the security boundary. The
                client never sees the key itself.
            connection_id: The specific AI connection ID to use. If None, uses the default.
        """
        self.ai_config = ai_config
        self._provider_factory = provider_factory

        requested_id = connection_id or ai_config.default_connection

        if requested_id and requested_id not in ai_config.connections:
            # Naming a connection that is gone - typically a default left behind by a rename -
            # is answered by saying so. Quietly using a different one would send the user's
            # prompts somewhere they never chose, and they would have no way to notice.
            raise AIConfigurationError(
                f"AI connection '{requested_id}' does not exist. "
                f"Pick one in AI Configuration (main menu)."
            )

        if requested_id:
            self.connection_id = requested_id
        elif ai_config.connections:
            self.connection_id = list(ai_config.connections.keys())[0]
        else:
            raise AIConfigurationError("No AI connections configured.")

        self._provider: Optional[AIProvider] = None

    @property
    def provider(self) -> AIProvider:
        """
        Get the configured AI adapter (lazy loading).

        Returns:
            AI adapter instance.

        Raises:
            AIConfigurationError: If AI is not enabled or configured incorrectly.
        """
        if self._provider:
            return self._provider

        connection_config = self.ai_config.connections.get(self.connection_id)
        if not connection_config:
            raise AIConfigurationError(
                f"AI connection '{self.connection_id}' not found in configuration."
            )

        self._provider = self._provider_factory(self.connection_id, connection_config)
        return self._provider

    def generate(
        self,
        messages: List[AIMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> AIResponse:
        """
        Generate a response using the configured AI connection.

        Args:
            messages: List of conversation messages.
            max_tokens: Optional override for the maximum number of tokens.
            temperature: Optional override for the temperature.
            json_schema: Accepted and ignored. Remote connections here do not
                enforce a response shape, and the caller validates the answer
                either way; the parameter exists so the same call works whether
                the answer comes from a connection or a local CLI.

        Returns:
            AI response with generated content.
        """
        connection_cfg = self.ai_config.connections.get(self.connection_id)
        if not connection_cfg:
            raise AIConfigurationError(
                f"AI connection '{self.connection_id}' not found for generation."
            )

        request = AIRequest(
            messages=messages,
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else (
                    None
                    if connection_cfg.connection_type == AIConnectionType.GATEWAY
                    else connection_cfg.max_tokens
                )
            ),
            temperature=(
                temperature
                if temperature is not None
                else (
                    None
                    if connection_cfg.connection_type == AIConnectionType.GATEWAY
                    else connection_cfg.temperature
                )
            ),
        )
        # The SDK's HTTP request blocks with no way to poll for app exit, so it
        # runs interruptibly: if the TUI closes mid-request, the workflow thread
        # aborts instead of hanging interpreter shutdown until the response lands.
        return run_interruptible(lambda: self.provider.generate(request))

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Simple chat interface for single-turn conversations.

        Args:
            prompt: User prompt/question.
            system_prompt: Optional system prompt to set context.
            max_tokens: Optional override for the maximum number of tokens.
            temperature: Optional override for the temperature.

        Returns:
            AI response text.
        """
        messages = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))

        response = self.generate(
            messages, max_tokens=max_tokens, temperature=temperature
        )
        return response.content

    def is_available(self) -> bool:
        """
        Check if AI is available and configured correctly.

        Returns:
            True if AI can be used.
        """
        if not self.ai_config or not self.ai_config.connections:
            return False

        connection_cfg = self.ai_config.connections.get(self.connection_id)
        if not connection_cfg:
            return False

        try:
            return self.provider is not None
        except AIConfigurationError:
            return False
