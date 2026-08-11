"""Tests for provider-level handling of models that refuse `temperature`."""

from titan_cli.ai.providers.sampling import (
    is_temperature_rejection,
    rejects_temperature,
    remember_temperature_rejection,
)


class TestKnownFamilies:
    """Recognized models never cost a failed request."""

    def test_known_families_are_recognized_up_front(self):
        assert rejects_temperature("claude-opus-5") is True
        assert rejects_temperature("claude-fable-5") is True

    def test_dated_and_prefixed_variants_are_recognized(self):
        assert rejects_temperature("claude-opus-5-20260101") is True
        assert rejects_temperature("anthropic/claude-opus-5") is True
        assert rejects_temperature("CLAUDE-OPUS-5") is True

    def test_other_models_are_left_alone(self):
        assert rejects_temperature("claude-sonnet-4-6") is False
        assert rejects_temperature("gpt-4o") is False
        assert rejects_temperature("gemma3:4b") is False


class TestLearnedRejections:
    """A gateway alias no list could predict is learned from the one failure it causes."""

    def test_an_unrecognized_alias_can_be_learned(self):
        assert rejects_temperature("acme-gateway-alias") is False
        remember_temperature_rejection("acme-gateway-alias")
        assert rejects_temperature("acme-gateway-alias") is True


class TestRejectionDetection:
    def test_detects_the_real_api_message(self):
        error = Exception(
            "litellm.BadRequestError: AnthropicException - "
            '{"error":{"message":"`temperature` is deprecated for this model."}}'
        )
        assert is_temperature_rejection(error) is True

    def test_ignores_unrelated_bad_requests(self):
        assert is_temperature_rejection(Exception("context length exceeded")) is False

    def test_ignores_a_temperature_range_complaint(self):
        """A value out of range is the caller's bug, not a refusal of the parameter."""
        assert is_temperature_rejection(Exception("temperature must be between 0 and 1")) is False

    def test_ignores_a_range_complaint_that_also_says_unsupported(self):
        """An out-of-range value borrows the refusal wording but must not disable the parameter."""
        error = Exception("temperature: 3.0 is not supported; must be between 0 and 1")
        assert is_temperature_rejection(error) is False
