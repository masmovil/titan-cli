"""
Tests for AI environment configuration detection
"""
import pytest
import os
from unittest.mock import patch
from titan_cli.ai.env_config import AIEnvDetector, get_env_aware_defaults, EnvAIConfig


class TestAIEnvDetector:
    """Test AIEnvDetector class"""

    def test_detect_no_env_vars(self):
        """Test detection with no environment variables"""
        with patch.dict(os.environ, {}, clear=True):
            config = AIEnvDetector.detect("anthropic")
            assert not config.detected
            assert config.provider is None
            assert config.base_url is None
            assert config.default_model is None

    def test_detect_anthropic_standard(self):
        """Test detection of standard Anthropic configuration"""
        # Clear all Anthropic-related env vars first
        env_vars = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
        env_vars["ANTHROPIC_API_KEY"] = "sk-ant-test123"

        with patch.dict(os.environ, env_vars, clear=True):
            config = AIEnvDetector.detect("anthropic")
            assert config.detected
            assert config.provider == "anthropic"
            assert config.api_key == "sk-ant-test123"
            assert config.base_url is None

    def test_detect_anthropic_corporate_gateway(self):
        """Test detection of corporate gateway"""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test123",
            "ANTHROPIC_BASE_URL": "https://llm.tools.cloud.masorange.es",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-5"
        }):
            config = AIEnvDetector.detect("anthropic")
            assert config.detected
            assert config.provider == "anthropic"
            assert config.base_url == "https://llm.tools.cloud.masorange.es"
            assert config.default_model == "claude-sonnet-4-5"

    def test_detect_openai(self):
        """Test detection of OpenAI configuration"""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-openai-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1"
        }):
            config = AIEnvDetector.detect("openai")
            assert config.detected
            assert config.provider == "openai"
            assert config.api_key == "sk-openai-test"
            assert config.base_url == "https://api.openai.com/v1"

    def test_detect_gemini(self):
        """Test detection of Gemini configuration"""
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "AIzaTest123"
        }):
            config = AIEnvDetector.detect("gemini")
            assert config.detected
            assert config.provider == "gemini"
            assert config.api_key == "AIzaTest123"

    def test_detect_all_providers(self):
        """Test detection of all providers"""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-openai-test",
            "GEMINI_API_KEY": "AIzaTest"
        }):
            configs = AIEnvDetector.detect_all()
            assert len(configs) == 3
            assert configs["anthropic"].detected
            assert configs["openai"].detected
            assert configs["gemini"].detected

    def test_get_suggested_config_with_gateway(self):
        """Test getting suggested config with corporate gateway"""
        with patch.dict(os.environ, {
            "ANTHROPIC_BASE_URL": "https://llm.corporate.com",
            "ANTHROPIC_DEFAULT_MODEL": "claude-custom"
        }):
            suggested = AIEnvDetector.get_suggested_config("anthropic")
            assert suggested["base_url"] == "https://llm.corporate.com"
            assert suggested["model"] == "claude-custom"
            assert suggested["is_custom_endpoint"] is True

    def test_get_suggested_config_standard(self):
        """Test getting suggested config without custom endpoint"""
        with patch.dict(os.environ, {}, clear=True):
            suggested = AIEnvDetector.get_suggested_config("anthropic")
            assert "base_url" not in suggested or suggested["base_url"] is None

    def test_is_corporate_gateway_true(self):
        """Test corporate gateway detection returns True"""
        with patch.dict(os.environ, {
            "ANTHROPIC_BASE_URL": "https://llm.corporate.com"
        }):
            assert AIEnvDetector.is_corporate_gateway("anthropic") is True

    def test_is_corporate_gateway_false(self):
        """Test corporate gateway detection returns False"""
        with patch.dict(os.environ, {}, clear=True):
            assert AIEnvDetector.is_corporate_gateway("anthropic") is False

    def test_get_gateway_info_with_gateway(self):
        """Test getting gateway info when gateway is configured"""
        with patch.dict(os.environ, {
            "ANTHROPIC_BASE_URL": "https://llm.tools.cloud.masorange.es",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-5"
        }):
            info = AIEnvDetector.get_gateway_info("anthropic")
            assert info is not None
            assert info["url"] == "https://llm.tools.cloud.masorange.es"
            assert info["domain"] == "llm.tools.cloud.masorange.es"
            assert info["model"] == "claude-sonnet-4-5"
            assert info["detected_from"] == "environment variables"

    def test_get_gateway_info_without_gateway(self):
        """Test getting gateway info when no gateway is configured"""
        with patch.dict(os.environ, {}, clear=True):
            info = AIEnvDetector.get_gateway_info("anthropic")
            assert info is None

    def test_env_aware_defaults_with_gateway(self):
        """Test env-aware defaults with corporate gateway"""
        with patch.dict(os.environ, {
            "ANTHROPIC_BASE_URL": "https://llm.corporate.com",
            "ANTHROPIC_DEFAULT_MODEL": "claude-custom"
        }):
            defaults = get_env_aware_defaults("anthropic")
            assert defaults["model"] == "claude-custom"
            assert defaults["base_url"] == "https://llm.corporate.com"
            assert defaults["is_custom_endpoint"] is True

    def test_env_aware_defaults_standard(self):
        """Test env-aware defaults without environment config"""
        with patch.dict(os.environ, {}, clear=True):
            defaults = get_env_aware_defaults("anthropic")
            # Should use standard defaults from constants
            assert defaults["model"] == "claude-3-5-sonnet-20241022"
            assert defaults["base_url"] is None
            assert defaults["is_custom_endpoint"] is False

    def test_model_priority_env_over_default(self):
        """Test that environment model takes priority over default"""
        with patch.dict(os.environ, {
            "ANTHROPIC_DEFAULT_MODEL": "claude-env-model"
        }):
            defaults = get_env_aware_defaults("anthropic")
            assert defaults["model"] == "claude-env-model"

    def test_multiple_model_env_vars(self):
        """Test handling of multiple model environment variables"""
        with patch.dict(os.environ, {
            "ANTHROPIC_DEFAULT_MODEL": "first-model",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "second-model"
        }):
            config = AIEnvDetector.detect("anthropic")
            # Should use first matching pattern
            assert config.default_model == "first-model"

    def test_env_config_dataclass(self):
        """Test EnvAIConfig dataclass"""
        config = EnvAIConfig(
            provider="anthropic",
            base_url="https://test.com",
            default_model="test-model",
            api_key="test-key",
            detected=True
        )
        assert config.provider == "anthropic"
        assert config.base_url == "https://test.com"
        assert config.default_model == "test-model"
        assert config.api_key == "test-key"
        assert config.detected is True
        assert config.source == "environment"
