"""Gemini AI provider (Google)

Supports both API key and OAuth authentication via gcloud.
Also supports custom endpoints with Anthropic-compatible API format."""

from .base import AIProvider
from ..models import AIRequest, AIResponse, AIMessage
from ..exceptions import AIProviderAPIError, AIProviderAuthenticationError, AIProviderRateLimitError

from ..constants import get_default_model

try:
    import google.generativeai as genai
    import google.auth
    from google.generativeai.types import GenerationConfig # Import GenerationConfig
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    
# For custom endpoint support
import requests
import json


class GeminiProvider(AIProvider):
    """
    Provider for Gemini API (Google).

    Supports:
    - API key authentication
    - OAuth via gcloud (Application Default Credentials)

    Requires:
    - pip install google-generativeai google-auth
    - API key from https://makersuite.google.com/app/apikey
    - OR: gcloud auth application-default login

    Usage:
        # With API key
        provider = GeminiProvider("AIza...", model="gemini-pro")

        # With OAuth (gcloud)
        provider = GeminiProvider("GCLOUD_OAUTH", model="gemini-pro")
    """

    def __init__(self, api_key: str, model: str = get_default_model("gemini"), base_url: str = None):
        super().__init__(api_key, model)

        # Normalize base_url by removing trailing slash
        self.base_url = base_url.rstrip('/') if base_url else None
        self.use_custom_endpoint = bool(base_url)

        # Check if using OAuth or API key
        self.use_oauth = (api_key == "GCLOUD_OAUTH")

        if self.use_custom_endpoint:
            # Custom endpoint mode - use HTTP requests manually
            # Corporate endpoint uses same API format as Anthropic
            if self.use_oauth:
                raise AIProviderAPIError(
                    "OAuth is not supported with custom endpoints. Please use an API key."
                )
            # No additional setup needed, will use requests directly
        else:
            # Standard Google Gemini endpoint - use google-generativeai library
            if not GEMINI_AVAILABLE:
                raise AIProviderAPIError(
                    "google-generativeai not installed.\n"
                    "Install with: poetry add google-generativeai google-auth"
                )

            if self.use_oauth:
                # Use Application Default Credentials
                try:
                    google.auth.default()
                    # Gemini will use ADC automatically
                except Exception as e:
                    raise AIProviderAPIError(
                        f"Failed to get Google Cloud credentials: {e}\n"
                        "Run: gcloud auth application-default login"
                    )
            else:
                # Use API key with official Google endpoint
                genai.configure(api_key=api_key)

    def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using Gemini API

        Args:
            request: AI request with messages

        Returns:
            AI response

        Raises:
            AIProviderAPIError: If generation fails
        """
        if self.use_custom_endpoint:
            return self._generate_custom_endpoint(request)
        else:
            return self._generate_google_endpoint(request)

    def _generate_custom_endpoint(self, request: AIRequest) -> AIResponse:
        """
        Generate using custom corporate endpoint.
        Uses same API format as Anthropic (messages API).
        """
        try:
            # Separate system messages from regular messages
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            regular_messages = [msg for msg in request.messages if msg.role != "system"]

            # Build system parameter
            system_content = "\n\n".join(msg.content for msg in system_messages) if system_messages else None

            # Convert messages to API format
            messages = [{"role": msg.role, "content": msg.content} for msg in regular_messages]

            # Build request payload
            payload = {
                "model": self.model,
                "max_tokens": request.max_tokens or 4096,
                "messages": messages
            }

            if system_content:
                payload["system"] = system_content

            if request.temperature is not None:
                payload["temperature"] = request.temperature

            # Build headers
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            # Make HTTP request
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                raise AIProviderAPIError(
                    f"Custom endpoint error: {response.status_code} - {response.text}"
                )

            data = response.json()

            # Extract response content (Anthropic format)
            content = ""
            if "content" in data and len(data["content"]) > 0:
                content = data["content"][0].get("text", "")

            # Handle empty content (e.g., max_tokens reached)
            if not content and data.get("stop_reason") == "max_tokens":
                raise AIProviderAPIError(
                    "Response truncated due to max_tokens limit. Increase max_tokens in request."
                )

            # Extract usage
            usage_data = {}
            if "usage" in data:
                usage_data = {
                    "input_tokens": data["usage"].get("input_tokens", 0),
                    "output_tokens": data["usage"].get("output_tokens", 0),
                }

            return AIResponse(
                content=content,
                model=data.get("model", self.model),
                usage=usage_data,
                finish_reason=data.get("stop_reason", "stop")
            )

        except requests.exceptions.RequestException as e:
            raise AIProviderAPIError(f"Custom endpoint request failed: {e}")
        except Exception as e:
            raise AIProviderAPIError(f"Gemini API error: {e}")

    def _generate_google_endpoint(self, request: AIRequest) -> AIResponse:
        """Generate using official Google Gemini endpoint"""
        try:
            # Convert messages to Gemini format
            gemini_messages = self._convert_messages(request.messages)

            # Get model
            model = genai.GenerativeModel(self.model)

            # Prepare generation config
            generation_config = GenerationConfig(
                temperature=request.temperature,
                max_output_tokens=request.max_tokens
            )

            # Generate response
            if len(gemini_messages) == 1 and gemini_messages[0].get("role") == "user":
                # Single message - use generate_content
                response = model.generate_content(
                    gemini_messages[0]["parts"],
                    generation_config=generation_config
                )
            else:
                # Multiple messages - use chat
                chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
                response = chat.send_message(
                    gemini_messages[-1]["parts"],
                    generation_config=generation_config
                )

            # Extract text
            text = response.text

            # Extract usage data if available
            usage_data = {}
            if hasattr(response, 'usage_metadata'):
                usage_data = {
                    "input_tokens": response.usage_metadata.prompt_token_count,
                    "output_tokens": response.usage_metadata.candidates_token_count,
                }

            return AIResponse(
                content=text,
                model=self.model,
                usage=usage_data,
                finish_reason="stop" # Not easily available in all cases
            )

        except Exception as e:
            raise AIProviderAPIError(f"Gemini API error: {e}")

    def _convert_messages(self, messages: list[AIMessage]) -> list[dict]:
        """
        Convert AIMessage format to Gemini format

        Gemini uses:
        - role: "user" or "model" (not "assistant")
        - parts: list of text content

        System messages are prepended to the first user message
        """
        gemini_messages = []
        system_context = ""

        for msg in messages:
            if msg.role == "system":
                # Accumulate system messages
                system_context += msg.content + "\n\n"
            elif msg.role == "user":
                content = msg.content
                if system_context:
                    # Prepend system context to first user message
                    content = f"{system_context}{content}"
                    system_context = ""

                gemini_messages.append({
                    "role": "user",
                    "parts": [content]
                })
            elif msg.role == "assistant":
                gemini_messages.append({
                    "role": "model",  # Gemini uses "model" instead of "assistant"
                    "parts": [msg.content]
                })

        return gemini_messages

    @property
    def name(self) -> str:
        return "gemini"
