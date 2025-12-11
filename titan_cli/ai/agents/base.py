# titan_cli/ai/agents/base.py
"""Base classes for AI agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Protocol, List

from titan_cli.ai.models import AIMessage, AIResponse


@dataclass
class AgentRequest:
    """Generic request for AI generation."""
    context: str
    max_tokens: int = 2000
    temperature: float = 0.7
    system_prompt: Optional[str] = None


@dataclass
class AgentResponse:
    """Generic response from AI generation."""
    content: str
    tokens_used: int
    provider: str
    cached: bool = False


class AIGenerator(Protocol):
    """
    Protocol defining the interface for AI generation.

    This allows BaseAIAgent to depend on an abstraction rather than
    concrete implementations like AIClient or AIProvider.

    Any class implementing these methods can be used with agents.
    """

    def generate(
        self,
        messages: List[AIMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AIResponse:
        """
        Generate AI response from messages.

        Args:
            messages: List of AIMessage objects
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            AIResponse object with content and metadata
        """
        ...

    def is_available(self) -> bool:
        """
        Check if AI generation is available.

        Returns:
            True if AI can be used
        """
        ...


class BaseAIAgent(ABC):
    """
    Abstract base class for all AI agents.

    Agents wrap AI generation with specialized domain logic.
    They depend on AIGenerator protocol for loose coupling.
    """

    def __init__(self, generator: AIGenerator):
        """
        Initialize agent with AI generator.

        Args:
            generator: Any object implementing AIGenerator protocol
                      (e.g., AIClient, AIProvider, or mock for testing)
        """
        self.generator = generator

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent's expertise.

        Each agent defines its specialized role.
        """
        pass

    def generate(self, request: AgentRequest) -> AgentResponse:
        """
        Generate AI response using the underlying generator.

        Args:
            request: AgentRequest with context and parameters

        Returns:
            AgentResponse with generated content
        """
        # Build messages with system prompt
        messages = []

        # Use agent's system prompt if not overridden
        system_prompt = request.system_prompt or self.get_system_prompt()
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))

        messages.append(AIMessage(role="user", content=request.context))

        # Call underlying generator (AIClient, AIProvider, etc.)
        response = self.generator.generate(
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )

        # Convert to AgentResponse
        # Calculate tokens used - handle both patterns
        if response.usage:
            # Try total_tokens first (some providers)
            tokens_used = response.usage.get("total_tokens", 0)

            # If not available, try input_tokens + output_tokens (Anthropic, etc.)
            if tokens_used == 0:
                input_tokens = response.usage.get("input_tokens", 0)
                output_tokens = response.usage.get("output_tokens", 0)
                tokens_used = input_tokens + output_tokens
        else:
            tokens_used = 0

        # Get provider name safely
        try:
            provider_obj = getattr(self.generator, '_provider', self.generator)
            provider_name = provider_obj.__class__.__name__ if provider_obj else "Unknown"
        except AttributeError:
            provider_name = "Unknown"

        return AgentResponse(
            content=response.content,
            tokens_used=tokens_used,
            provider=provider_name,
            cached=False
        )

    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.generator and self.generator.is_available()
