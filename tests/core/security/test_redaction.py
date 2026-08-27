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


# --- Fixes from the PR #261 review round ---

def test_find_secret_in_checks_dict_keys():
    from titan_cli.core.security.redaction import find_secret_in, register_secret
    register_secret("sk-secret-as-a-key")
    found = find_secret_in({"outer": {"sk-secret-as-a-key": "value"}})
    assert found is not None
    # The reported path must not echo the secret itself.
    assert "sk-secret-as-a-key" not in found


def test_short_secret_still_detected_even_if_not_substituted():
    """Detection must not lose short secrets to the display heuristic."""
    from titan_cli.core.security.redaction import contains_secret, find_secret_in, register_secret, redact
    register_secret("ab1")
    assert contains_secret("prefix ab1 suffix") is True
    assert find_secret_in({"x": "ab1"}) is not None
    # Substitution keeps the length floor: no shredding of unrelated text.
    assert redact("ab1 and absolute") == "ab1 and absolute"


def test_find_secret_in_survives_self_referencing_structure():
    from titan_cli.core.security.redaction import find_secret_in, register_secret
    register_secret("cyclic-secret-value")
    d = {"ok": "clean"}
    d["self"] = d
    assert find_secret_in(d) is None  # terminates, no RecursionError
    d["leak"] = "cyclic-secret-value"
    assert find_secret_in(d) is not None
