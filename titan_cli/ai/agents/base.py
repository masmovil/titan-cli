# titan_cli/ai/agents/base.py
"""Base classes for AI agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from titan_cli.ai.client import AIClient


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


class BaseAIAgent(ABC):
    """
    Abstract base class for all AI agents.

    Agents wrap AIClient with specialized domain logic.
    They receive AIClient as dependency and use it for generation.
    """

    def __init__(self, ai_client: "AIClient"):
        """
        Initialize agent with AIClient.

        Args:
            ai_client: The AIClient instance (manages providers)
        """
        self.ai_client = ai_client

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent's expertise.

        Each agent defines its specialized role.
        """
        pass

    def generate(self, request: AgentRequest) -> AgentResponse:
        """
        Generate AI response using the underlying AIClient.

        Args:
            request: AgentRequest with context and parameters

        Returns:
            AgentResponse with generated content
        """
        from titan_cli.ai.models import AIMessage

        # Build messages
        messages = [AIMessage(role="user", content=request.context)]

        # Use agent's system prompt if not overridden
        system_prompt = request.system_prompt or self.get_system_prompt()

        # Call underlying AIClient (which delegates to provider)
        response = self.ai_client.generate(
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system_prompt=system_prompt
        )

        # Convert to AgentResponse
        return AgentResponse(
            content=response.content,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            provider=self.ai_client._provider.__class__.__name__,
            cached=False
        )

    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.ai_client and self.ai_client.is_available()
