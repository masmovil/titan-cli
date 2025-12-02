"""
OpenAI provider (ChatGPT) - STUB

TODO: Implement it. Now it's not working
"""

from .base import AIProvider
from ..models import AIRequest, AIResponse
from ..exceptions import AIProviderAPIError


from ..constants import get_default_model


class OpenAIProvider(AIProvider):
    """
    Provider for OpenAI API (ChatGPT).

    Requires:
    - pip install openai
    - API key from https://platform.openai.com/api-keys

    Status: NOT IMPLEMENTED YET
    """

    def __init__(self, api_key: str, model: str = get_default_model("openai")):
        super().__init__(api_key, model)
        # TODO: Initialize OpenAI client
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI provider requires 'openai' library.\n"
                "Install with: poetry add openai"
            )


    def generate(self, request: AIRequest) -> AIResponse:
        """Generate response using OpenAI API"""
        raise AIProviderAPIError(
            "OpenAI provider is not implemented yet.\n"
            "Use 'anthropic' or 'gemini' provider for now, or implement this provider."
        )

    @property
    def name(self) -> str:
        return "openai"
