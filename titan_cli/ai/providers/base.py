"""
Base AI provider interface
"""

from abc import ABC, abstractmethod

from ..models import AIRequest, AIResponse


class AIProvider(ABC):
    """
    Base interface for AI providers.

    Each provider implements how to interact with a specific AI API
    (Claude, Gemini, OpenAI, etc.)
    """

    def __init__(self, api_key: str, model: str):
        """
        Initialize provider.

        Args:
            api_key: API key for the provider
            model: Model identifier (e.g., "claude-3-5-sonnet-20241022")
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using the AI model.

        Args:
            request: Request with messages and parameters

        Returns:
            Response with generated content

        Raises:
            AIProviderError: If generation fails
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider name (e.g., "claude", "gemini", "openai").

        Returns:
            Provider identifier
        """
        pass

    def validate_api_key(self) -> bool:
        """
        Validate that the API key works.

        Returns:
            True if API key is valid

        Note: Default implementation tries a simple generation.
              Providers can override for more efficient validation.
        """
        try:
            from ..models import AIMessage
            test_request = AIRequest(
                messages=[AIMessage(role="user", content="Hi")],
                max_tokens=10
            )
            self.generate(test_request)
            return True
        except Exception:
            return False
