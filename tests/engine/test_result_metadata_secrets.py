"""
Result-metadata leak checks: Success/Skip/Exit metadata is merged into
ctx.data and may be logged, so constructing one with a registered secret
string inside raises at the step that leaked it.
"""

import pytest

from titan_cli.core.security import SecretLeakError, SensitiveValue
from titan_cli.core.security.redaction import clear_registry, register_secret
from titan_cli.engine.results import Exit, Skip, Success


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    register_secret("sk-registered-secret-value")
    yield
    clear_registry()


@pytest.mark.parametrize("result_cls", [Success, Skip, Exit])
def test_metadata_with_secret_string_raises(result_cls):
    with pytest.raises(SecretLeakError, match="token"):
        result_cls("msg", metadata={"token": "sk-registered-secret-value"})


def test_metadata_with_embedded_secret_raises():
    with pytest.raises(SecretLeakError):
        Success("msg", metadata={"cmd": "curl -H 'sk-registered-secret-value'"})


def test_nested_metadata_is_scanned():
    with pytest.raises(SecretLeakError, match="auth.headers"):
        Success("msg", metadata={"auth": {"headers": ["sk-registered-secret-value"]}})


def test_clean_metadata_passes():
    r = Success("msg", metadata={"pr_number": 123, "note": "all good"})
    assert r.metadata == {"pr_number": 123, "note": "all good"}


def test_sensitive_value_is_allowed_in_metadata():
    # Opaque carriers are the sanctioned way for derived material to travel.
    sv = SensitiveValue("derived-material-xyz-123")
    r = Success("msg", metadata={"sa": sv})
    assert r.metadata["sa"] is sv


def test_no_metadata_is_fine():
    assert Success("msg").metadata is None
    assert Skip("msg").metadata is None
    assert Exit("msg").metadata is None
