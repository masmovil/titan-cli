"""
AI Client - Main facade for AI functionality

This client provides two modes:
1. Simple text generation (generate/chat methods)
2. Tool calling with TAP for autonomous agents (generate_with_tools method)
"""

from typing import Optional, List, Any
from pathlib import Path

from titan_cli.core.config import TitanConfig
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
    - Reading configuration from TitanConfig.
    - Retrieving secrets from SecretManager.
    - Instantiating the correct AI provider.
    - Providing a simple `generate()` and `chat()` interface.
    """

    def __init__(self, titan_config: TitanConfig, secrets: SecretManager):
        """
        Initialize AI client.

        Args:
            titan_config: The main TitanConfig object.
            secrets: The SecretManager for handling API keys.
        """
        self.titan_config = titan_config
        self.secrets = secrets
        self._provider: Optional[AIProvider] = None
        self._tap_manager: Optional[Any] = None  # TAP manager for tool calling

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

        ai_config = self.titan_config.config.ai
        if not ai_config:
            raise AIConfigurationError("AI configuration section is missing in config.")

        provider_name = ai_config.provider
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
        kwargs = {"api_key": api_key, "model": ai_config.model}
        if ai_config.base_url:
            kwargs["base_url"] = ai_config.base_url

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
        ai_config = self.titan_config.config.ai
        if not ai_config:
            raise AIConfigurationError("AI configuration section is missing.")

        request = AIRequest(
            messages=messages,
            max_tokens=max_tokens if max_tokens is not None else ai_config.max_tokens,
            temperature=temperature if temperature is not None else ai_config.temperature,
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

    # =========================================================================
    # TAP Integration - Tool Calling Support
    # =========================================================================

    @property
    def tap(self) -> Any:
        """
        Get TAP manager for tool calling (lazy loading).

        Returns:
            TAPManager instance.

        Raises:
            AIConfigurationError: If TAP configuration is missing.
        """
        if self._tap_manager:
            return self._tap_manager

        # Lazy import to avoid circular dependencies
        from titan_cli.tap import TAPManager

        ai_config = self.titan_config.config.ai
        if not ai_config:
            raise AIConfigurationError("AI configuration section is missing.")

        provider_name = ai_config.provider
        api_key = self.secrets.get(f"{provider_name}_api_key")

        if not api_key:
            raise AIConfigurationError(f"API key for {provider_name} not found.")

        # Initialize TAP with config
        tap_config_path = Path(__file__).parent.parent.parent / "config" / "tap" / "adapters.yml"

        if tap_config_path.exists():
            self._tap_manager = TAPManager.from_config(str(tap_config_path))
        else:
            # Fallback: initialize without config
            self._tap_manager = TAPManager()

        return self._tap_manager

    def generate_with_tools(
        self,
        prompt: str,
        tools: List[Any],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Generate response with tool calling support (TAP-powered).

        This method enables autonomous AI agents that can decide which tools to use.

        Args:
            prompt: User prompt/question.
            tools: List of TitanTool instances available to the agent.
            system_prompt: Optional system prompt.
            max_tokens: Optional max tokens override.
            temperature: Optional temperature override.

        Returns:
            Dictionary with:
                - content: Final response text
                - tool_calls: List of tools used
                - iterations: Number of tool calling iterations

        Example:
            from titan_cli.core.plugins.tool_base import TitanTool

            tools = [read_file_tool, write_file_tool, run_tests_tool]

            response = ai_client.generate_with_tools(
                prompt="Fix the bug in main.py",
                tools=tools
            )

            print(response['content'])  # AI's final answer
            print(response['tool_calls'])  # Tools it used
        """
        ai_config = self.titan_config.config.ai
        if not ai_config:
            raise AIConfigurationError("AI configuration section is missing.")

        provider_name = ai_config.provider

        # Get TAP adapter for provider
        try:
            adapter = self.tap.get(provider_name)
        except KeyError:
            raise AIConfigurationError(
                f"Tool calling not supported for provider: {provider_name}"
            )

        # Convert tools to provider format using TAP
        converted_tools = adapter.convert_tools(tools)

        # Use provider's native SDK for tool calling
        # This is provider-specific implementation
        if provider_name == "anthropic":
            return self._anthropic_tool_calling(
                prompt,
                converted_tools,
                tools,
                system_prompt,
                max_tokens or ai_config.max_tokens,
                temperature or ai_config.temperature
            )
        elif provider_name == "openai":
            return self._openai_tool_calling(
                prompt,
                converted_tools,
                tools,
                system_prompt,
                max_tokens or ai_config.max_tokens,
                temperature or ai_config.temperature
            )
        else:
            raise AIConfigurationError(
                f"Tool calling not supported for provider: {provider_name}"
            )

    def _anthropic_tool_calling(
        self,
        prompt: str,
        converted_tools: List[dict],
        original_tools: List[Any],
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> dict[str, Any]:
        """Execute tool calling with Anthropic Claude."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.secrets.get("anthropic_api_key"))
        model = self.titan_config.config.ai.model or "claude-sonnet-4-20250514"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        tool_calls_made = []
        iterations = 0
        max_iterations = 10  # Prevent infinite loops

        while iterations < max_iterations:
            iterations += 1

            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
                tools=converted_tools
            )

            # Check if AI wants to use tools
            if response.stop_reason == "tool_use":
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input

                        # Execute tool using TAP adapter
                        adapter = self.tap.get("anthropic")
                        tool_result = adapter.execute_tool(
                            tool_name,
                            tool_input,
                            original_tools
                        )

                        tool_calls_made.append({
                            "tool": tool_name,
                            "input": tool_input,
                            "output": tool_result
                        })

                        # Add tool result to conversation
                        messages.append({
                            "role": "assistant",
                            "content": response.content
                        })
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": content_block.id,
                                "content": str(tool_result)
                            }]
                        })
            else:
                # AI finished, return final response
                return {
                    "content": response.content[0].text if response.content else "",
                    "tool_calls": tool_calls_made,
                    "iterations": iterations
                }

        # Max iterations reached
        return {
            "content": "Max iterations reached",
            "tool_calls": tool_calls_made,
            "iterations": iterations
        }

    def _openai_tool_calling(
        self,
        prompt: str,
        converted_tools: List[dict],
        original_tools: List[Any],
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> dict[str, Any]:
        """Execute tool calling with OpenAI GPT."""
        # TODO: Implement OpenAI function calling
        raise NotImplementedError("OpenAI tool calling not yet implemented")
