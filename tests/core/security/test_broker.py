import copy
import json
import pickle
from unittest.mock import patch

import pytest

from titan_cli.core.security import SecretBroker, SecretLeakError, SecretRef, redaction
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


def test_create_client_passes_value_into_builder_only(vault, mock_keyring):
    """The secret crosses into the constructor; the caller gets the object."""
    mock_keyring[0].side_effect = lambda ns, k: (
        "tok_value" if (ns, k) == ("titan.plugins.demo", "token") else None
    )
    broker = SecretBroker(vault, "titan.plugins.demo")

    class Client:
        def __init__(self, token):
            self.authorization = f"Bearer {token}"

    client = broker.create_client("token", Client)

    assert isinstance(client, Client)
    assert client.authorization == "Bearer tok_value"
    # The dereference registered the value for redaction.
    assert redaction.redact("x tok_value y") == f"x {redaction.REDACTED} y"


def test_create_client_identity_builder_is_rejected(vault, mock_keyring):
    """A builder that hands the value back out raises instead of leaking."""
    mock_keyring[0].return_value = "tok_value"
    broker = SecretBroker(vault, "titan.plugins.demo")

    with pytest.raises(SecretLeakError):
        broker.create_client("token", lambda v: v)


def test_create_client_string_embedding_value_is_rejected(vault, mock_keyring):
    """Formatted strings carrying the secret are a leak, not a client."""
    mock_keyring[0].return_value = "tok_value"
    broker = SecretBroker(vault, "titan.plugins.demo")

    with pytest.raises(SecretLeakError):
        broker.create_client("token", lambda v: f"Bearer {v}")

    with pytest.raises(SecretLeakError):
        broker.create_client("token", lambda v: f"auth: {v}".encode())


def test_create_client_missing_key_raises(vault, mock_keyring):
    mock_keyring[0].return_value = None
    broker = SecretBroker(vault, "titan.plugins.demo")

    with pytest.raises(KeyError, match="titan.plugins.demo:token"):
        broker.create_client("token", lambda v: v)


def test_create_client_optional_missing_builds_with_none(vault, mock_keyring):
    mock_keyring[0].return_value = None
    broker = SecretBroker(vault, "titan.plugins.demo")

    sentinel = object()
    result = broker.create_client(
        "token", lambda v: sentinel if v is None else None, required=False
    )

    assert result is sentinel


def test_store_writes_value_and_returns_ref(vault, mock_keyring):
    """A value the caller already holds flows in; only an opaque ref comes back."""
    broker = SecretBroker(vault, "titan.core")
    ref = broker.store("api_key", "typed_into_a_form")

    mock_keyring[1].assert_called_once_with("titan.core", "api_key", "typed_into_a_form")
    assert ref == SecretRef("titan.core", "api_key")
    assert redaction.redact("x typed_into_a_form y") == f"x {redaction.REDACTED} y"


def test_prompt_and_store_without_prompter_raises(vault):
    broker = SecretBroker(vault, "titan.core")
    with pytest.raises(RuntimeError, match="no prompter"):
        broker.prompt_and_store("token", "Enter")


def test_delete_uses_broker_namespace_and_sweeps_legacy(vault, mock_keyring):
    """Delete must also clear the legacy service names: a copy left there
    would be resurrected by the lazy-migration fallback on the next read."""
    broker = SecretBroker(vault, "titan.plugins.demo")
    broker.delete("token")
    deleted = [call.args for call in mock_keyring[2].call_args_list]
    assert deleted[0] == ("titan.plugins.demo", "token")
    assert ("titan", "token") in deleted
    assert ("ragnarok", "token") in deleted


# --- Fixes from the PR #261 review round ---

def test_store_rejects_empty_value(vault):
    broker = SecretBroker(vault, "titan.plugins.demo")
    with pytest.raises(ValueError):
        broker.store("token", "")
    with pytest.raises(ValueError):
        broker.store("token", "   ")


def test_stdin_primitive_keeps_stored_secret_on_exec_failure(vault):
    """Exit 127 (command not found) says nothing about the credential."""
    with patch('keyring.get_password', return_value="stored-pass"), \
         patch('keyring.delete_password') as mock_delete:
        broker = SecretBroker(vault, "titan.plugins.demo")
        result = broker.run_with_secret_stdin(
            "passphrase", "Passphrase:", ["definitely-not-a-command-xyz"]
        )
    assert result.exit_code in (126, 127)
    mock_delete.assert_not_called()


# --- Fixes from the PR #261 second review round ---

@pytest.fixture
def env_isolated():
    import os
    from unittest.mock import patch as _patch
    with _patch.dict(os.environ, clear=True):
        yield


@pytest.fixture
def keyring_store(env_isolated):
    store = {}
    with patch('keyring.get_password', side_effect=lambda ns, k: store.get((ns, k))), \
         patch('keyring.set_password', side_effect=lambda ns, k, v: store.__setitem__((ns, k), v)), \
         patch('keyring.delete_password', side_effect=lambda ns, k: store.pop((ns, k), None)):
        yield store


def test_delete_returns_true_when_gone(keyring_store, tmp_path):
    keyring_store[("titan.plugins.demo", "token")] = "v"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.delete("token") is True
    assert broker.exists("token") is False


def test_delete_returns_false_when_env_shadows(keyring_store, tmp_path):
    import os
    os.environ["TOKEN"] = "from-env"
    keyring_store[("titan.plugins.demo", "token")] = "v"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.delete("token") is False
    assert broker.exists("token") is True  # env copy survives — visibly


def test_delete_sweeps_legacy_so_nothing_resurrects(keyring_store, tmp_path):
    """Behavioral pin: after delete, the lazy fallback cannot resurrect it."""
    keyring_store[("titan.plugins.demo", "token")] = "scoped"
    keyring_store[("titan", "token")] = "legacy"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.delete("token") is True
    assert broker.exists("token") is False
    assert keyring_store == {}


def test_source_reports_cascade_level(keyring_store, tmp_path):
    import os
    keyring_store[("titan.plugins.demo", "kr_key")] = "v"
    os.environ["ENV_KEY"] = "v"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.source("kr_key") == "keyring"
    assert broker.source("env_key") == "env"
    assert broker.source("missing") is None


def test_stdin_retry_does_not_delete_when_value_came_from_env(keyring_store, tmp_path):
    """A failing command must not nuke keyring state for an env-sourced value."""
    import os
    os.environ["PASSPHRASE"] = "from-env"
    keyring_store[("titan.plugins.demo", "passphrase")] = "unrelated-keyring-copy"
    prompts = []
    broker = SecretBroker(
        SecretManager(project_path=tmp_path), "titan.plugins.demo",
        prompter=lambda p: prompts.append(p) or "typed",
    )
    result = broker.run_with_secret_stdin("passphrase", "Pass:", ["false"])
    assert result.exit_code != 0
    assert prompts == []  # no re-prompt loop
    assert keyring_store[("titan.plugins.demo", "passphrase")] == "unrelated-keyring-copy"


def test_stdin_retry_replaces_keyring_value_on_any_command_failure(keyring_store, tmp_path):
    """Pinned semantics: ANY command failure (except exec failures 126/127
    and timeouts) triggers replace — the broker cannot generically tell a
    bad credential from another failure, so it re-prompts once."""
    keyring_store[("titan.plugins.demo", "passphrase")] = "stale"
    broker = SecretBroker(
        SecretManager(project_path=tmp_path), "titan.plugins.demo",
        prompter=lambda p: "fresh",
    )
    result = broker.run_with_secret_stdin("passphrase", "Pass:", ["false"])
    assert result.exit_code != 0  # command still fails, but the retry ran
    assert keyring_store[("titan.plugins.demo", "passphrase")] == "fresh"


# --- derive_namespace / for_plugin coverage ---

def test_derive_namespace_mapping():
    from titan_cli.core.security.broker import derive_namespace
    assert derive_namespace("slack") == "titan.plugins.slack"
    assert derive_namespace(None) == "titan.core"
    assert derive_namespace("core") == "titan.core"
    assert derive_namespace("project") == "titan.project"
    assert derive_namespace("user") == "titan.user"


def test_for_plugin_scopes_broker(tmp_path):
    from titan_cli.core.security.broker import SecretBrokerFactory
    factory = SecretBrokerFactory(SecretManager(project_path=tmp_path))
    assert factory.for_plugin("slack").namespace == "titan.plugins.slack"
    assert factory.for_plugin("core").namespace == "titan.core"


def test_reserved_plugin_names_rejected_at_registration():
    from titan_cli.core.plugins.plugin_registry import _reject_reserved_plugin_name
    for name in ("core", "project", "user"):
        with pytest.raises(ValueError, match="reserved"):
            _reject_reserved_plugin_name(name)
    _reject_reserved_plugin_name("slack")  # normal names pass


# --- public API allowlist (replaces enumeration-based read checks) ---

def test_broker_public_api_is_exactly_the_allowlist():
    allowed = {
        "exists", "source", "store", "prompt_and_store", "delete",
        "create_client", "run_with_secret_stdin", "run_with_secret_env",
        "with_secret_tempfile", "namespace",
    }
    public = {n for n in dir(SecretBroker) if not n.startswith("_")}
    assert public == allowed, (
        "SecretBroker's public surface changed. Adding a method here is a "
        "deliberate act: anything value-returning breaks the no-read guarantee."
    )


# --- Fixes from the PR #261 third review round ---

def test_prompt_and_store_rejects_empty_and_whitespace(keyring_store, tmp_path):
    for typed in ("", "   "):
        broker = SecretBroker(
            SecretManager(project_path=tmp_path), "titan.plugins.demo",
            prompter=lambda p, t=typed: t,
        )
        assert broker.prompt_and_store("token", "Token:") is None
    assert keyring_store == {}


def test_source_reports_project_level(keyring_store, tmp_path):
    (tmp_path / ".titan").mkdir()
    (tmp_path / ".titan" / "secrets.env").write_text("FILE_KEY='v'\n")
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.source("file_key") == "project"


def test_delete_returns_false_when_project_file_shadows(keyring_store, tmp_path):
    (tmp_path / ".titan").mkdir()
    (tmp_path / ".titan" / "secrets.env").write_text("TOKEN='file-copy'\n")
    keyring_store[("titan.plugins.demo", "token")] = "kr-copy"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.delete("token") is False
    assert broker.exists("token") is True


def test_stdin_retry_does_not_delete_when_value_came_from_project_file(keyring_store, tmp_path):
    (tmp_path / ".titan").mkdir()
    (tmp_path / ".titan" / "secrets.env").write_text("PASSPHRASE='file-pass'\n")
    keyring_store[("titan.plugins.demo", "passphrase")] = "keyring-copy"
    prompts = []
    broker = SecretBroker(
        SecretManager(project_path=tmp_path), "titan.plugins.demo",
        prompter=lambda p: prompts.append(p) or "typed",
    )
    result = broker.run_with_secret_stdin("passphrase", "Pass:", ["false"])
    assert result.exit_code != 0
    assert prompts == []
    assert keyring_store[("titan.plugins.demo", "passphrase")] == "keyring-copy"


def test_namespaces_isolate_same_key(keyring_store, tmp_path):
    """A backend ignoring the namespace parameter must fail the suite."""
    vault = SecretManager(project_path=tmp_path)
    SecretBroker(vault, "titan.plugins.a").store("token", "value-a")
    SecretBroker(vault, "titan.plugins.b").store("token", "value-b")
    assert keyring_store[("titan.plugins.a", "token")] == "value-a"
    assert keyring_store[("titan.plugins.b", "token")] == "value-b"


# --- Fourth review round ---

def test_delete_when_shadowed_still_removes_keyring_copy(keyring_store, tmp_path):
    import os
    os.environ["TOKEN"] = "from-env"
    keyring_store[("titan.plugins.demo", "token")] = "kr-copy"
    broker = SecretBroker(SecretManager(project_path=tmp_path), "titan.plugins.demo")
    assert broker.delete("token") is False  # env shadow survives...
    assert keyring_store == {}              # ...but the keyring copy is gone
