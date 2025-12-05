"""
AI Environment Configuration Helper

Detects and uses environment variables for AI configuration,
particularly useful for corporate gateways and custom endpoints.
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EnvAIConfig:
    """Detected AI configuration from environment variables"""
    provider: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    api_key: Optional[str] = None
    detected: bool = False
    source: str = "environment"


class AIEnvDetector:
    """
    Detects AI configuration from environment variables.

    Supports multiple patterns:
    - Standard: ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
    - Base URL: ANTHROPIC_BASE_URL, OPENAI_BASE_URL, etc.
    - Models: ANTHROPIC_DEFAULT_MODEL, ANTHROPIC_DEFAULT_SONNET_MODEL, etc.
    """

    # Environment variable patterns for each provider
    ENV_PATTERNS = {
        "anthropic": {
            "api_key": ["ANTHROPIC_API_KEY"],
            "base_url": ["ANTHROPIC_BASE_URL"],
            "model": [
                "ANTHROPIC_DEFAULT_MODEL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL",
                "ANTHROPIC_MODEL"
            ]
        },
        "openai": {
            "api_key": ["OPENAI_API_KEY"],
            "base_url": ["OPENAI_BASE_URL", "OPENAI_API_BASE"],
            "model": ["OPENAI_DEFAULT_MODEL", "OPENAI_MODEL"]
        },
        "gemini": {
            "api_key": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "base_url": ["GEMINI_BASE_URL"],
            "model": ["GEMINI_DEFAULT_MODEL", "GEMINI_MODEL"]
        }
    }

    @classmethod
    def detect(cls, provider: str) -> EnvAIConfig:
        """
        Detect AI configuration for a provider from environment variables.

        Args:
            provider: Provider key (anthropic, openai, gemini)

        Returns:
            EnvAIConfig with detected values
        """
        config = EnvAIConfig()

        if provider not in cls.ENV_PATTERNS:
            return config

        patterns = cls.ENV_PATTERNS[provider]

        # Detect API key
        for key_var in patterns.get("api_key", []):
            value = os.getenv(key_var)
            if value:
                config.api_key = value
                config.detected = True
                break

        # Detect base URL (custom endpoint/gateway)
        for url_var in patterns.get("base_url", []):
            value = os.getenv(url_var)
            if value:
                config.base_url = value
                config.detected = True
                break

        # Detect default model
        for model_var in patterns.get("model", []):
            value = os.getenv(model_var)
            if value:
                config.default_model = value
                config.detected = True
                break

        if config.detected:
            config.provider = provider

        return config

    @classmethod
    def detect_all(cls) -> Dict[str, EnvAIConfig]:
        """
        Detect configuration for all providers.

        Returns:
            Dictionary mapping provider -> EnvAIConfig
        """
        return {
            provider: cls.detect(provider)
            for provider in cls.ENV_PATTERNS.keys()
        }

    @classmethod
    def get_suggested_config(cls, provider: str) -> Dict[str, Any]:
        """
        Get suggested configuration for a provider based on env vars.

        Args:
            provider: Provider key

        Returns:
            Dictionary with suggested config values
        """
        env_config = cls.detect(provider)
        suggested = {}

        if env_config.base_url:
            suggested["base_url"] = env_config.base_url
            suggested["is_custom_endpoint"] = True

        if env_config.default_model:
            suggested["model"] = env_config.default_model

        return suggested

    @classmethod
    def is_corporate_gateway(cls, provider: str) -> bool:
        """
        Check if a corporate gateway is configured via env vars.

        Args:
            provider: Provider key

        Returns:
            True if base_url env var is set (indicates gateway)
        """
        env_config = cls.detect(provider)
        return env_config.base_url is not None

    @classmethod
    def get_gateway_info(cls, provider: str) -> Optional[Dict[str, str]]:
        """
        Get information about detected corporate gateway.

        Args:
            provider: Provider key

        Returns:
            Dictionary with gateway info or None
        """
        env_config = cls.detect(provider)

        if not env_config.base_url:
            return None

        # Extract domain for display
        from urllib.parse import urlparse
        parsed = urlparse(env_config.base_url)
        domain = parsed.netloc or parsed.path

        return {
            "url": env_config.base_url,
            "domain": domain,
            "model": env_config.default_model,
            "detected_from": "environment variables"
        }


def get_env_aware_defaults(provider: str) -> Dict[str, Any]:
    """
    Get defaults that are aware of environment configuration.

    This is a convenience function that combines standard defaults
    with environment-detected values.

    Args:
        provider: Provider key

    Returns:
        Dictionary with default configuration
    """
    from .constants import get_default_model

    defaults = {
        "model": get_default_model(provider),
        "base_url": None,
        "is_custom_endpoint": False
    }

    # Override with environment suggestions
    env_suggestions = AIEnvDetector.get_suggested_config(provider)
    defaults.update(env_suggestions)

    return defaults
