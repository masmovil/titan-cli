import pytest
from pydantic import ValidationError

from titan_cli.core.models import AIProviderConfig, AIConfig


def test_aiproviderconfig_full_fields():
    """Test AIProviderConfig with all possible fields."""
    config = AIProviderConfig(
        name="Test Provider",
        type="individual",
        provider="anthropic",
        model="claude-sonnet",
        base_url="https://api.example.com",
        temperature=0.5,
        max_tokens=1024,
    )
    assert config.name == "Test Provider"
    assert config.type == "individual"
    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet"
    assert config.base_url == "https://api.example.com"
    assert config.temperature == 0.5
    assert config.max_tokens == 1024


def test_aiproviderconfig_required_fields():
    """Test AIProviderConfig with only required fields."""
    config = AIProviderConfig(
        name="Minimal Provider",
        type="corporate",
        provider="gemini",
        model="gemini-pro",
    )
    assert config.name == "Minimal Provider"
    assert config.type == "corporate"
    assert config.provider == "gemini"
    assert config.model == "gemini-pro"
    assert config.base_url is None
    assert config.temperature == 0.7  # Default value
    assert config.max_tokens == 4096  # Default value


def test_aiproviderconfig_missing_required_fields():
    """Test AIProviderConfig raises ValidationError for missing required fields."""
    with pytest.raises(ValidationError, match="name"):
        AIProviderConfig(type="individual", provider="anthropic", model="claude-sonnet")
    with pytest.raises(ValidationError, match="type"):
        AIProviderConfig(name="Bad Provider", provider="anthropic", model="claude-sonnet")
    with pytest.raises(ValidationError, match="provider"):
        AIProviderConfig(name="Bad Provider", type="individual", model="claude-sonnet")


def test_aiconfig_multiple_providers_and_default():
    """Test AIConfig with multiple providers and a default."""
    config = AIConfig(
        default="corp-gemini",
        providers={
            "corp-gemini": AIProviderConfig(
                name="Corporate Gemini",
                type="corporate",
                provider="gemini",
                model="gemini-2.0",
                temperature=0.8,
            ),
            "personal-claude": AIProviderConfig(
                name="Personal Claude",
                type="individual",
                provider="anthropic",
                model="claude-3",
                max_tokens=4096,
            ),
        },
    )
    assert config.default == "corp-gemini"
    assert "corp-gemini" in config.providers
    assert "personal-claude" in config.providers

    corp_gemini = config.providers["corp-gemini"]
    assert corp_gemini.name == "Corporate Gemini"
    assert corp_gemini.provider == "gemini"
    assert corp_gemini.temperature == 0.8

    personal_claude = config.providers["personal-claude"]
    assert personal_claude.name == "Personal Claude"
    assert personal_claude.provider == "anthropic"
    assert personal_claude.max_tokens == 4096


def test_aiconfig_no_providers():
    """Test AIConfig with no providers."""
    config = AIConfig(providers={})
    assert config.default == "default"
    assert not config.providers


def test_aiconfig_default_not_in_providers():
    """Test AIConfig raises ValidationError if default provider is not in providers."""
    with pytest.raises(ValidationError):
        AIConfig(
            default="non-existent",
            providers={
                "corp-gemini": AIProviderConfig(
                    name="Corporate Gemini",
                    type="corporate",
                    provider="gemini",
                    model="gemini-2.0",
                )
            },
        )


def test_aiconfig_empty_providers_with_default():
    """Test AIConfig raises ValidationError if default is set but providers is empty."""
    with pytest.raises(ValidationError):
        AIConfig(default="some-default", providers={})


