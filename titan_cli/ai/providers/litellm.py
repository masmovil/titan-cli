"""
LiteLLM Provider - OpenAI-compatible endpoints (LiteLLM, vLLM, etc.)

Supports any OpenAI-compatible API endpoint, including:
- LiteLLM proxy servers
- vLLM inference servers
- Custom on-premise deployments
- Other OpenAI-compatible services
"""

from collections.abc import Mapping, Sequence
from typing import Optional

try:
    from openai import (
        APIError,
        AuthenticationError,
        OpenAI,
        OpenAIError,
        RateLimitError,
    )
    OPENAI_AVAILABLE = True
    OPENAI_IMPORT_ERROR = None
except ImportError as e:
    OpenAI = None
    OpenAIError = Exception
    APIError = Exception
    AuthenticationError = Exception
    RateLimitError = Exception
    OPENAI_AVAILABLE = False
    OPENAI_IMPORT_ERROR = str(e)

from .base import AIProvider
from .sampling import (
    is_temperature_rejection,
    rejects_temperature,
    remember_temperature_rejection,
)
from ..litellm_client import LiteLLMClient
from ..models import AIRequest, AIResponse
from ..exceptions import (
    AIProviderAuthenticationError,
    AIProviderRateLimitError,
    AIProviderAPIError,
)


class LiteLLMProvider(AIProvider):
    """
    LiteLLM/OpenAI-compatible provider.

    Uses the OpenAI Python SDK to communicate with any OpenAI-compatible API.
    This includes LiteLLM proxy servers, vLLM, and custom deployments.

    Args:
        base_url: The base URL of the API endpoint (required)
        model: Model name/identifier (required)
        api_key: API key for authentication (optional - some endpoints don't require auth)
        max_tokens: Maximum tokens in response (default: 4096)
        temperature: Sampling temperature 0-1 (default: 0.7)
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """Initialize LiteLLM provider with OpenAI-compatible client."""
        if not base_url:
            raise ValueError("base_url is required for LiteLLM provider")

        if not model:
            raise ValueError("model is required for LiteLLM provider")

        if not OPENAI_AVAILABLE:
            error_msg = "LiteLLM provider requires 'openai' library.\n"
            if OPENAI_IMPORT_ERROR:
                error_msg += f"Import error: {OPENAI_IMPORT_ERROR}\n"
            error_msg += "Install with: poetry add openai"
            raise ImportError(error_msg)

        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        gateway_client = LiteLLMClient(base_url=base_url, api_key=api_key)
        self._base_url = gateway_client.base_url
        self._http_client = gateway_client._http_client
        self._client = gateway_client._client

    @property
    def name(self) -> str:
        """Provider name."""
        return f"litellm ({self._base_url})"

    def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate completion using custom OpenAI-compatible endpoint.

        Args:
            request: AI request with messages, max_tokens, temperature

        Returns:
            AI response with generated content

        Raises:
            AIProviderAuthenticationError: Invalid API key
            AIProviderRateLimitError: Rate limit exceeded
            AIProviderAPIError: Other API errors
        """
        try:
            # Convert AIMessage list to OpenAI format
            messages = [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
            ]

            request_kwargs = {
                "model": self._model,
                "messages": messages,
                "stream": False,
            }

            if request.max_tokens is not None:
                request_kwargs["max_tokens"] = request.max_tokens

            if request.temperature is not None and not rejects_temperature(self._model):
                request_kwargs["temperature"] = request.temperature

            response = self._create_completion(request_kwargs)
            choice = response.choices[0]
            usage = response.usage
            response_model = response.model or self._model
            finish_reason = choice.finish_reason or "stop"
            content = self._extract_choice_content(choice)

            if not content and finish_reason == "length":
                raise AIProviderAPIError(
                    "LiteLLM response was truncated before yielding textual content."
                )

            return AIResponse(
                content=content,
                model=response_model,
                usage=(
                    {
                        "input_tokens": usage.prompt_tokens,
                        "output_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                    }
                    if usage
                    else {}
                ),
                finish_reason=finish_reason,
            )

        except AuthenticationError as e:
            raise AIProviderAuthenticationError(
                f"Authentication failed for LiteLLM endpoint: {str(e)}"
            )
        except RateLimitError as e:
            raise AIProviderRateLimitError(
                f"Rate limit exceeded for LiteLLM endpoint: {str(e)}"
            )
        except APIError as e:
            raise AIProviderAPIError(
                f"API error from LiteLLM endpoint: {str(e)}"
            )
        except OpenAIError as e:
            raise AIProviderAPIError(
                f"LiteLLM provider error: {str(e)}"
            )

    def _create_completion(self, request_kwargs: dict):
        """
        Send the completion request, retrying without `temperature` if the model refuses it.

        Some models reject the parameter instead of ignoring it, which fails the whole
        request. The retry costs one extra round trip the first time a given model is used;
        after that the model is remembered and `temperature` is never sent to it again.
        """
        try:
            return self._client.chat.completions.create(**request_kwargs)
        except APIError as e:
            if "temperature" not in request_kwargs or not is_temperature_rejection(e):
                raise
            remember_temperature_rejection(self._model)
            del request_kwargs["temperature"]
            return self._client.chat.completions.create(**request_kwargs)

    @classmethod
    def _extract_choice_content(cls, choice) -> str:
        """Extract text content robustly from OpenAI-compatible response choices."""
        message = getattr(choice, "message", None)
        direct_content = getattr(message, "content", None)
        text = cls._coerce_content_to_text(direct_content)
        if text:
            return text

        if message is not None and hasattr(message, "model_dump"):
            text = cls._extract_text_from_mapping(message.model_dump())
            if text:
                return text

        if hasattr(choice, "model_dump"):
            text = cls._extract_text_from_mapping(choice.model_dump())
            if text:
                return text

        return ""

    @classmethod
    def _extract_text_from_mapping(cls, data) -> str:
        if not isinstance(data, Mapping):
            return ""

        for key in ("content", "text", "output_text", "reasoning_content"):
            text = cls._coerce_content_to_text(data.get(key))
            if text:
                return text

        for key in (
            "parts",
            "candidates",
            "output",
            "outputs",
            "message",
            "provider_payload",
            "provider_response",
            "raw_response",
            "response",
        ):
            text = cls._coerce_content_to_text(data.get(key))
            if text:
                return text

        return ""

    @classmethod
    def _coerce_content_to_text(cls, content) -> str:
        if content is None:
            return ""

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, Mapping):
            if "text" in content and isinstance(content["text"], str):
                return content["text"].strip()
            if "parts" in content:
                return cls._coerce_content_to_text(content["parts"])
            if "candidates" in content:
                return cls._coerce_content_to_text(content["candidates"])
            if "output" in content:
                return cls._coerce_content_to_text(content["output"])
            if "outputs" in content:
                return cls._coerce_content_to_text(content["outputs"])
            if "content" in content:
                return cls._coerce_content_to_text(content["content"])
            if "message" in content:
                return cls._coerce_content_to_text(content["message"])
            if "provider_payload" in content:
                return cls._coerce_content_to_text(content["provider_payload"])
            if "provider_response" in content:
                return cls._coerce_content_to_text(content["provider_response"])
            if "raw_response" in content:
                return cls._coerce_content_to_text(content["raw_response"])
            if "response" in content:
                return cls._coerce_content_to_text(content["response"])
            return ""

        if isinstance(content, Sequence) and not isinstance(
            content, (str, bytes, bytearray)
        ):
            parts = [cls._coerce_content_to_text(item) for item in content]
            return "\n".join(part for part in parts if part).strip()

        return ""

    def validate_api_key(self, api_key: Optional[str] = None) -> bool:
        """
        Validate API key by making a minimal test request.

        Args:
            api_key: Optional API key to test (uses instance key if not provided)

        Returns:
            True if valid, False otherwise

        Note:
            Some custom endpoints don't require API keys.
            In that case, this method attempts a test request to validate connectivity.
        """
        try:
            LiteLLMClient(
                base_url=self._base_url,
                api_key=api_key or self._client.api_key,
            ).test_connection(model=self._model)
            return True
        except AuthenticationError:
            return False
        except Exception:
            # Other errors (rate limit, model not found, etc.) mean auth is OK
            # The endpoint is reachable and auth passed
            return True
