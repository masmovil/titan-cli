"""SensitiveValue: opaque, non-serializable, redaction-registered."""

import copy
import json
import pickle

import pytest

from titan_cli.core.security import SensitiveValue
from titan_cli.core.security.redaction import clear_registry, redact


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


def test_reveal_returns_payload():
    sv = SensitiveValue({"private_key": "-----BEGIN PRIVATE KEY-----abc"})
    assert sv.reveal() == {"private_key": "-----BEGIN PRIVATE KEY-----abc"}


def test_repr_and_str_never_show_payload():
    sv = SensitiveValue("hunter2-super-secret")
    assert "hunter2" not in repr(sv)
    assert "hunter2" not in str(sv)
    assert "REDACTED" in repr(sv)


def test_not_picklable():
    with pytest.raises(TypeError):
        pickle.dumps(SensitiveValue("s3cret-value"))


def test_not_deepcopyable():
    with pytest.raises(TypeError):
        copy.deepcopy(SensitiveValue("s3cret-value"))


def test_not_json_serializable():
    with pytest.raises(TypeError):
        json.dumps({"sa": SensitiveValue("s3cret-value")})


def test_immutable():
    sv = SensitiveValue("s3cret-value")
    with pytest.raises(AttributeError):
        sv._value = "other"


def test_string_payload_registered_for_redaction():
    SensitiveValue("tok-abcdef123456")
    assert redact("leaked tok-abcdef123456 here") == "leaked [REDACTED] here"


def test_long_container_leaves_registered_short_ones_not():
    SensitiveValue({
        "type": "sa",  # short: must NOT be globally redacted
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvz\n-----END-----",
    })
    assert redact("type sa ok") == "type sa ok"
    assert "BEGIN PRIVATE KEY" not in redact(
        "dump: -----BEGIN PRIVATE KEY-----\nMIIEvz\n-----END-----"
    )


def test_nested_container_leaves_registered():
    SensitiveValue({"outer": {"token": "nested-secret-token-value"}})
    assert redact("x nested-secret-token-value y") == "x [REDACTED] y"
