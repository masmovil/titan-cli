"""
AI Provider Constants

Minimal constants for AI providers. Models are not hardcoded to allow
for easy updates and custom/enterprise model support.
"""

from typing import Dict


# Default models (can be overridden by user)
PROVIDER_DEFAULTS: Dict[str, str] = {
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini-1.5-pro",
}


# Provider metadata
PROVIDER_INFO: Dict[str, Dict[str, str]] = {
    "anthropic": {
        "name": "Claude (Anthropic)",
        "api_key_url": "https://console.anthropic.com/",
        "api_key_prefix": "sk-ant-",
    },
    "gemini": {
        "name": "Gemini (Google)",
        "api_key_url": "https://makersuite.google.com/app/apikey",
        "api_key_prefix": "AIza",
    },
}


def get_default_model(provider: str) -> str:
    """
    Get default model for a provider

    Args:
        provider: Provider key (e.g., "anthropic")

    Returns:
        Default model string
    """
    return PROVIDER_DEFAULTS.get(provider, "")


def get_provider_name(provider: str) -> str:
    """
    Get human-readable provider name

    Args:
        provider: Provider key

    Returns:
        Provider display name
    """
    return PROVIDER_INFO.get(provider, {}).get("name", provider.title())
