# titan_cli/ai/agents/base.py
"""Base classes for AI agents."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Protocol, List

from titan_cli.ai.agents.contracts import AgentContract
from titan_cli.ai.exceptions import AIResponseParseError
from titan_cli.ai.models import AIMessage, AIResponse
from titan_cli.core.logging.config import get_logger


@dataclass
class AgentRequest:
    """
    Generic request for AI generation.

    `contract` has no default on purpose: every call states the shape of answer
    it needs, so a new agent cannot silently depend on whatever the model felt
    like returning. When the answer really is prose, `TextContract()` says so.
    """
    context: str
    contract: AgentContract
    max_tokens: int = 2000
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    operation: str = ""  # Label for logging (e.g., "commit_message", "pr_description")


@dataclass
class AgentResponse:
    """Generic response from AI generation."""
    content: str
    tokens_used: int
    provider: str
    cached: bool = False
    parsed: Any = None  # The contract's output: a mapping, a string, whatever it declared
    contract_degraded: bool = False  # The contract's defaults were used after a failed retry


class AIGenerator(Protocol):
    """
    Protocol defining the interface for AI generation.

    This allows BaseAIAgent to depend on an abstraction rather than
    concrete implementations like AIClient or AIProvider.

    Any class implementing these methods can be used with agents. It is also
    the only seam an agent is allowed to reach: keeping every agent on this
    interface, and nothing below it, is what lets the same agent run against a
    remote connection or a local CLI without knowing which.
    """

    def generate(
        self,
        messages: List[AIMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> AIResponse:
        """
        Generate AI response from messages.

        Args:
            messages: List of AIMessage objects
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            json_schema: Shape the answer should take, for generators able to
                enforce one. Honoring it is optional, so callers must still
                validate what comes back.

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
                      (e.g., AIClient, HeadlessGenerator, or mock for testing)
        """
        self.generator = generator
        self._logger = get_logger(__name__)

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent's expertise.

        Each agent defines its specialized role.
        """
        pass

    def generate(self, request: AgentRequest) -> AgentResponse:
        """
        Generate an AI response and recover the shape the request declared.

        A response that does not match the contract earns exactly one repair
        attempt, which asks the model to reshape its own previous answer. That
        retry runs regardless of transport and regardless of whether a schema
        was sent: a provider can accept a schema and still answer in prose, so
        the parse result - not the provider's promise - decides.

        Args:
            request: AgentRequest with context, parameters and its contract

        Returns:
            AgentResponse whose `parsed` holds the contract's output

        Raises:
            AIResponseParseError: the contract could not be satisfied twice and
                declares no degraded value.
        """
        contract = request.contract
        provider_name = self._provider_name()
        schema = contract.json_schema()

        messages = self._build_messages(request)
        response = self._call(messages, request, provider_name, schema)
        tokens_used = self._tokens_used(response)

        parsed = contract.parse(response.content)

        if not parsed.ok:
            self._logger.info(
                "ai_contract_parse_failed",
                provider=provider_name,
                operation=request.operation or "unknown",
                attempt=1,
                error=parsed.error,
                response_chars=len(response.content or ""),
            )
            repair = [
                AIMessage(role="user", content=contract.repair_prompt(response.content))
            ]
            response = self._call(repair, request, provider_name, schema)
            tokens_used += self._tokens_used(response)
            parsed = contract.parse(response.content)

        if not parsed.ok:
            degraded = contract.degraded_value()
            if degraded is None:
                self._logger.error(
                    "ai_contract_failed",
                    provider=provider_name,
                    operation=request.operation or "unknown",
                    error=parsed.error,
                    excerpt=(response.content or "")[:200],
                )
                raise AIResponseParseError(
                    f"{request.operation or 'This AI call'} did not return the expected "
                    f"format after a retry: {parsed.error}"
                )

            self._logger.info(
                "ai_contract_degraded",
                provider=provider_name,
                operation=request.operation or "unknown",
                error=parsed.error,
            )
            return AgentResponse(
                content=response.content,
                tokens_used=tokens_used,
                provider=provider_name,
                parsed=degraded,
                contract_degraded=True,
            )

        return AgentResponse(
            content=response.content,
            tokens_used=tokens_used,
            provider=provider_name,
            parsed=parsed.data,
        )

    def is_available(self) -> bool:
        """Check if AI is available."""
        return self.generator and self.generator.is_available()

    def _build_messages(self, request: AgentRequest) -> List[AIMessage]:
        """
        Build the conversation for one call.

        The contract's format instructions go last, after the agent's own
        prompt, so the shape is the final thing the model reads - and so each
        agent has one source of truth for it instead of a hand-written block
        that can drift from what the parser expects.
        """
        messages = []

        system_prompt = request.system_prompt or self.get_system_prompt()
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))

        content = request.context
        instructions = request.contract.format_instructions()
        if instructions:
            content = f"{content}\n\n{instructions}"

        messages.append(AIMessage(role="user", content=content))
        return messages

    def _call(
        self,
        messages: List[AIMessage],
        request: AgentRequest,
        provider_name: str,
        json_schema: Optional[dict],
    ) -> AIResponse:
        """Run one generation, logging its outcome."""
        start = time.time()
        try:
            response = self.generator.generate(
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                json_schema=json_schema,
            )
        except Exception:
            self._logger.debug(
                "ai_call_failed",
                provider=provider_name,
                operation=request.operation or "unknown",
                max_tokens=request.max_tokens,
                duration=round(time.time() - start, 3),
            )
            raise

        self._logger.debug(
            "ai_call_ok",
            provider=provider_name,
            operation=request.operation or "unknown",
            tokens=self._tokens_used(response),
            max_tokens=request.max_tokens,
            duration=round(time.time() - start, 3),
        )
        return response

    def _provider_name(self) -> str:
        """Best-effort name of whatever is actually generating, for logs."""
        try:
            provider_obj = getattr(self.generator, '_provider', self.generator)
            return provider_obj.__class__.__name__ if provider_obj else "Unknown"
        except AttributeError:
            return "Unknown"

    @staticmethod
    def _tokens_used(response: AIResponse) -> int:
        """
        Token count from whichever shape the provider reports.

        A CLI reports none at all, which is why zero is a normal answer here
        rather than a sign something went wrong.
        """
        if not response.usage:
            return 0

        total = response.usage.get("total_tokens", 0)
        if total:
            return total

        return response.usage.get("input_tokens", 0) + response.usage.get("output_tokens", 0)
