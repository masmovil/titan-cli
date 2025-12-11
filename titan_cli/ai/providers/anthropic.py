"""
Anthropic AI provider (Claude)
"""

from .base import AIProvider
from ..models import AIRequest, AIResponse
from ..exceptions import (
    AIProviderAuthenticationError,
    AIProviderRateLimitError,
    AIProviderAPIError
)


from ..constants import get_default_model


class AnthropicProvider(AIProvider):
    """
    Provider for Claude API (Anthropic).

    Requires:
    - pip install anthropic
    - API key from https://console.anthropic.com/
    """

    def __init__(self, api_key: str, model: str = get_default_model("anthropic"), base_url: str = None):
        super().__init__(api_key, model)
        try:
            from anthropic import Anthropic
            # Support custom base_url for enterprise endpoints
            # Normalize base_url by removing trailing slash
            normalized_base_url = base_url.rstrip('/') if base_url else None
            if normalized_base_url:
                self.client = Anthropic(api_key=api_key, base_url=normalized_base_url)
            else:
                self.client = Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "Anthropic provider requires 'anthropic' library.\n"
                "Install with: poetry add anthropic"
            )

    def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using Claude API.

        Args:
            request: Request with messages and parameters

        Returns:
            Response with generated content

        Raises:
            AIProviderAuthenticationError: Invalid API key
            AIProviderRateLimitError: Rate limit exceeded
            AIProviderAPIError: Other API errors
        """
        try:
            # Separate system messages from other messages
            # Claude API requires system as a top-level parameter, not in messages array
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            regular_messages = [msg for msg in request.messages if msg.role != "system"]

            # Build system parameter (combine all system messages)
            system_content = "\n\n".join(msg.content for msg in system_messages) if system_messages else None

            # Convert regular messages to Claude format
            messages = [msg.to_dict() for msg in regular_messages]

            # Call Claude API with system as separate parameter
            api_params = {
                "model": self.model,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "messages": messages
            }

            if system_content:
                api_params["system"] = system_content

            response = self.client.messages.create(**api_params)

            return AIResponse(
                content=response.content[0].text,
                model=response.model,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                },
                finish_reason=response.stop_reason
            )

        except Exception as e:
            error_msg = str(e).lower()

            if "authentication" in error_msg or "api key" in error_msg:
                raise AIProviderAuthenticationError(
                    f"Anthropic authentication failed: {e}\n"
                    f"Check your API key via `titan ai configure`"
                )
            elif "rate limit" in error_msg:
                raise AIProviderRateLimitError(
                    f"Anthropic rate limit exceeded: {e}\n"
                    f"Wait a moment and try again"
                )
            else:
                raise AIProviderAPIError(f"Anthropic API error: {e}")

    @property
    def name(self) -> str:
        return "anthropic"
