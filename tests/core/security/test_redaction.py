import pytest

from titan_cli.core.security import redaction


@pytest.fixture(autouse=True)
def clean_registry():
    redaction.clear_registry()
    yield
    redaction.clear_registry()


def test_redact_registered_value():
    redaction.register_secret("hunter2secret")
    assert redaction.redact("the password is hunter2secret!") == (
        f"the password is {redaction.REDACTED}!"
    )


def test_redact_multiple_values():
    redaction.register_secret("first_secret")
    redaction.register_secret("second_secret")
    out = redaction.redact("a=first_secret b=second_secret")
    assert "first_secret" not in out
    assert "second_secret" not in out


def test_redact_longest_first():
    # A secret containing another is masked whole, not left half-exposed.
    redaction.register_secret("token")
    redaction.register_secret("token-extended-form")
    out = redaction.redact("value: token-extended-form")
    assert out == f"value: {redaction.REDACTED}"


def test_short_values_not_registered():
    redaction.register_secret("ab")
    assert redaction.redact("ab is everywhere: absolute") == "ab is everywhere: absolute"


def test_empty_and_none_ignored():
    redaction.register_secret("")
    redaction.register_secret(None)
    assert redaction.redact("anything") == "anything"


def test_redact_empty_text():
    redaction.register_secret("some_secret")
    assert redaction.redact("") == ""
    assert redaction.redact(None) is None
