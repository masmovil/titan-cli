import copy
import json
import pickle
from unittest.mock import patch

import pytest

from titan_cli.core.security import SecretBroker, SecretRef, redaction
from titan_cli.core.security._vault import SecretManager


@pytest.fixture(autouse=True)
def clean_redaction_registry():
    redaction.clear_registry()
    yield
    redaction.clear_registry()


@pytest.fixture
def mock_keyring():
    with patch('keyring.get_password') as mock_get, \
         patch('keyring.set_password') as mock_set, \
         patch('keyring.delete_password') as mock_delete:
        yield mock_get, mock_set, mock_delete


@pytest.fixture
def vault(tmp_path):
    return SecretManager(project_path=tmp_path)


# --- SecretRef opacity ---

def test_secret_ref_repr_is_opaque():
    ref = SecretRef("titan.plugins.slack", "bot_token")
    assert repr(ref) == "SecretRef(titan.plugins.slack:bot_token)"
    assert str(ref) == "SecretRef(titan.plugins.slack:bot_token)"


def test_secret_ref_not_picklable():
    ref = SecretRef("titan.core", "api_key")
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(ref)


def test_secret_ref_not_json_serializable():
    ref = SecretRef("titan.core", "api_key")
    with pytest.raises(TypeError):
        json.dumps(ref)
    with pytest.raises(TypeError):
        json.dumps({"data": ref})


def test_secret_ref_not_deepcopyable():
    ref = SecretRef("titan.core", "api_key")
    with pytest.raises(TypeError, match="not serializable"):
        copy.deepcopy(ref)


def test_secret_ref_equality_and_hash():
    a = SecretRef("ns", "k")
    b = SecretRef("ns", "k")
    c = SecretRef("ns", "other")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)


# --- SecretBroker API surface ---

def test_broker_has_no_read_api(vault):
    broker = SecretBroker(vault, "titan.core")
    for forbidden in ("get", "get_value", "get_raw", "list"):
        assert not hasattr(broker, forbidden)


def test_exists_true_and_false(vault, mock_keyring):
    broker = SecretBroker(vault, "titan.plugins.demo")
    mock_keyring[0].return_value = "value"
    assert broker.exists("token") is True
    mock_keyring[0].assert_called_with("titan.plugins.demo", "token")

    mock_keyring[0].return_value = None
    assert broker.exists("missing") is False


def test_prompt_and_store_uses_broker_namespace(vault, mock_keyring):
    broker = SecretBroker(vault, "titan.plugins.demo", prompter=lambda prompt: "typed_secret")
    ref = broker.prompt_and_store("token", "Enter your token")

    mock_keyring[1].assert_called_once_with("titan.plugins.demo", "token", "typed_secret")
    assert ref == SecretRef("titan.plugins.demo", "token")
    # The stored value is registered for redaction immediately.
    assert redaction.redact("x typed_secret y") == f"x {redaction.REDACTED} y"


def test_prompt_and_store_cancelled_returns_none(vault, mock_keyring):
    broker = SecretBroker(vault, "titan.core", prompter=lambda prompt: None)
    assert broker.prompt_and_store("token", "Enter") is None
    mock_keyring[1].assert_not_called()


def test_prompt_and_store_without_prompter_raises(vault):
    broker = SecretBroker(vault, "titan.core")
    with pytest.raises(RuntimeError, match="no prompter"):
        broker.prompt_and_store("token", "Enter")


def test_delete_uses_broker_namespace(vault, mock_keyring):
    broker = SecretBroker(vault, "titan.plugins.demo")
    broker.delete("token")
    mock_keyring[2].assert_called_once_with("titan.plugins.demo", "token")
