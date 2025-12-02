"""Gemini AI provider (Google)

Supports both API key and OAuth authentication via gcloud."""

from .base import AIProvider
from ..models import AIRequest, AIResponse, AIMessage
from ..exceptions import AIProviderAPIError

from ..constants import get_default_model

try:
    import google.generativeai as genai
    import google.auth
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


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
        provider = GeminiProvider("AIza...", model="gemini-1.5-pro")

        # With OAuth (gcloud)
        provider = GeminiProvider("GCLOUD_OAUTH", model="gemini-1.5-pro")
    """

    def __init__(self, api_key: str, model: str = get_default_model("gemini")):
        if not GEMINI_AVAILABLE:
            raise AIProviderAPIError(
                "google-generativeai not installed.\n"
                "Install with: poetry add google-generativeai google-auth"
            )

        super().__init__(api_key, model)

        # Check if using OAuth or API key
        self.use_oauth = (api_key == "GCLOUD_OAUTH")

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
            # Use API key
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
        try:
            # Convert messages to Gemini format
            gemini_messages = self._convert_messages(request.messages)

            # Get model
            model = genai.GenerativeModel(self.model)

            # Generate response
            if len(gemini_messages) == 1 and gemini_messages[0].get("role") == "user":
                # Single message - use generate_content
                response = model.generate_content(gemini_messages[0]["parts"])
            else:
                # Multiple messages - use chat
                chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
                response = chat.send_message(gemini_messages[-1]["parts"])

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
