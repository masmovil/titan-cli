# titan_cli/ai/agents/base.py
"""Base classes for AI agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Protocol, List, TYPE_CHECKING

# Use TYPE_CHECKING for forward references only (not for runtime)
if TYPE_CHECKING:
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
        messages: "List[AIMessage]",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> "AIResponse":
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
        from titan_cli.ai.models import AIMessage

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
        return AgentResponse(
            content=response.content,
            tokens_used=response.usage.get("total_tokens", 0) if response.usage else 0,
            provider=getattr(self.generator, '_provider', self.generator).__class__.__name__,
            cached=False
        )

    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.generator and self.generator.is_available()
