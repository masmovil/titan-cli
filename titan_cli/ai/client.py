"""
AI Client - Main facade for AI functionality
"""

from typing import Optional, List

from titan_cli.core.models import AIConfig
from titan_cli.core.secrets import SecretManager
from .models import AIMessage, AIRequest, AIResponse
from .providers import AIProvider, AnthropicProvider, GeminiProvider, OpenAIProvider
from .exceptions import AIConfigurationError

# A mapping from provider names to classes
PROVIDER_CLASSES = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}

class AIClient:
    """
    Main client for AI functionality.

    This facade simplifies AI usage by:
    - Reading configuration from AIConfig.
    - Retrieving secrets from SecretManager.
    - Instantiating the correct AI provider.
    - Providing a simple `generate()` and `chat()` interface.
    """

    def __init__(self, ai_config: AIConfig, secrets: SecretManager):
        """
        Initialize AI client.

        Args:
            ai_config: The AI configuration.
            secrets: The SecretManager for handling API keys.
        """
        self.ai_config = ai_config
        self.secrets = secrets
        self._provider: Optional[AIProvider] = None

    @property
    def provider(self) -> AIProvider:
        """
        Get configured provider (lazy loading).

        Returns:
            Provider instance.

        Raises:
            AIConfigurationError: If AI is not enabled or configured incorrectly.
        """
        if self._provider:
            return self._provider

        provider_name = self.ai_config.provider
        provider_class = PROVIDER_CLASSES.get(provider_name)

        if not provider_class:
            raise AIConfigurationError(f"Unknown AI provider: {provider_name}")

        # Get API key
        api_key = self.secrets.get(f"{provider_name}_api_key")

        # Special case for Gemini OAuth
        if provider_name == "gemini" and self.secrets.get("gemini_oauth_enabled"):
            api_key = "GCLOUD_OAUTH"

        if not api_key:
            raise AIConfigurationError(f"API key for {provider_name} not found.")

        # Get base_url from config if exists (for custom endpoints)
        kwargs = {"api_key": api_key, "model": self.ai_config.model}
        if self.ai_config.base_url:
            kwargs["base_url"] = self.ai_config.base_url

        self._provider = provider_class(**kwargs)
        return self._provider

    def generate(
        self,
        messages: List[AIMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AIResponse:
        """
        Generate response using configured AI provider.

        Args:
            messages: List of conversation messages.
            max_tokens: Optional override for the maximum number of tokens.
            temperature: Optional override for the temperature.

        Returns:
            AI response with generated content.
        """
        request = AIRequest(
            messages=messages,
            max_tokens=max_tokens if max_tokens is not None else self.ai_config.max_tokens,
            temperature=temperature if temperature is not None else self.ai_config.temperature,
        )
        return self.provider.generate(request)

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
        try:
            # This will attempt to instantiate the provider, which includes key checks.
            return self.provider is not None
        except AIConfigurationError:
            return False
