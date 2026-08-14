import os
from unittest.mock import patch

import pytest

from titan_cli.core.security import redaction
from titan_cli.core.security._vault import SecretManager


@pytest.fixture(autouse=True)
def clean_redaction_registry():
    redaction.clear_registry()
    yield
    redaction.clear_registry()


@pytest.fixture
def tmp_project_path(tmp_path):
    (tmp_path / ".titan").mkdir()
    return tmp_path


@pytest.fixture
def mock_env():
    with patch.dict(os.environ, clear=True):
        yield


@pytest.fixture
def mock_keyring():
    with patch('keyring.get_password') as mock_get, \
         patch('keyring.set_password') as mock_set, \
         patch('keyring.delete_password') as mock_delete:
        yield mock_get, mock_set, mock_delete


# --- Project secrets stay out of os.environ ---

def test_project_secrets_loaded_in_memory_not_environ(tmp_project_path, mock_env, mock_keyring):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("MY_TOKEN='tok_value'\n")

    sm = SecretManager(project_path=tmp_project_path)

    assert "MY_TOKEN" not in os.environ
    assert sm.get("my_token") == "tok_value"


def test_no_project_secrets_file(tmp_project_path, mock_env, mock_keyring):
    mock_keyring[0].return_value = None
    sm = SecretManager(project_path=tmp_project_path)
    assert sm.get("anything") is None


# --- get cascade ---

def test_get_from_env(mock_env, mock_keyring):
    os.environ["MY_ENV_SECRET"] = "env_value"
    sm = SecretManager()
    assert sm.get("my_env_secret") == "env_value"
    mock_keyring[0].assert_not_called()


def test_get_from_keyring(mock_env, mock_keyring):
    mock_keyring[0].return_value = "keyring_value"
    sm = SecretManager()
    assert sm.get("my_keyring_secret") == "keyring_value"
    mock_keyring[0].assert_called_once_with("titan", "my_keyring_secret")


def test_get_keyring_namespace_passthrough(mock_env, mock_keyring):
    mock_keyring[0].return_value = "value"
    sm = SecretManager()
    sm.get("key", namespace="titan.plugins.slack")
    mock_keyring[0].assert_called_once_with("titan.plugins.slack", "key")


def test_get_none_if_not_found(mock_env, mock_keyring):
    mock_keyring[0].return_value = None
    sm = SecretManager()
    assert sm.get("non_existent_secret") is None


def test_get_priority_env_over_keyring(mock_env, mock_keyring):
    os.environ["SHARED_SECRET"] = "env_value"
    mock_keyring[0].return_value = "keyring_value"
    sm = SecretManager()
    assert sm.get("shared_secret") == "env_value"
    mock_keyring[0].assert_not_called()


def test_get_priority_env_over_project(tmp_project_path, mock_env, mock_keyring):
    (tmp_project_path / ".titan" / "secrets.env").write_text("SHARED='from_project'\n")
    os.environ["SHARED"] = "from_env"
    sm = SecretManager(project_path=tmp_project_path)
    assert sm.get("shared") == "from_env"


def test_get_priority_project_over_keyring(tmp_project_path, mock_env, mock_keyring):
    (tmp_project_path / ".titan" / "secrets.env").write_text("SHARED='from_project'\n")
    mock_keyring[0].return_value = "from_keyring"
    sm = SecretManager(project_path=tmp_project_path)
    assert sm.get("shared") == "from_project"
    mock_keyring[0].assert_not_called()


# --- redaction on dereference ---

def test_get_registers_value_in_redaction(mock_env, mock_keyring):
    mock_keyring[0].return_value = "super_secret_value"
    sm = SecretManager()
    sm.get("api_key")
    assert redaction.redact("prefix super_secret_value suffix") == (
        f"prefix {redaction.REDACTED} suffix"
    )


# --- set ---

def test_set_user_scope(mock_keyring):
    sm = SecretManager()
    sm.set("my_user_secret", "user_value", scope="user")
    mock_keyring[1].assert_called_once_with("titan", "my_user_secret", "user_value")


def test_set_user_scope_raises_when_keyring_write_fails(mock_keyring, tmp_project_path):
    mock_keyring[1].side_effect = RuntimeError("keyring unavailable")
    sm = SecretManager(project_path=tmp_project_path)

    with pytest.raises(RuntimeError, match="keyring unavailable"):
        sm.set("my_user_secret", "user_value", scope="user")

    # Regression: a user-scope failure must NEVER fall back to the
    # team-shared project file.
    assert not (tmp_project_path / ".titan" / "secrets.env").exists()


def test_set_project_scope_new_secret(tmp_project_path):
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("my_project_secret", "project_value", scope="project")

    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    assert secrets_file.exists()
    assert 'MY_PROJECT_SECRET="project_value"' in secrets_file.read_text()


def test_set_project_scope_update_secret(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("EXISTING_SECRET='old_value'\nOTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("existing_secret", "new_value", scope="project")

    content = secrets_file.read_text()
    assert 'EXISTING_SECRET="new_value"' in content
    assert "OTHER_KEY='other_value'" in content
    assert "EXISTING_SECRET='old_value'" not in content


def test_set_project_scope_visible_without_reload(tmp_project_path, mock_env, mock_keyring):
    mock_keyring[0].return_value = None
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("fresh_secret", "fresh_value", scope="project")
    assert sm.get("fresh_secret") == "fresh_value"
    assert "FRESH_SECRET" not in os.environ


def test_set_project_scope_creates_dir_if_not_exists(tmp_path):
    project_path = tmp_path / "new_project"
    sm = SecretManager(project_path=project_path)
    sm.set("new_secret", "value", scope="project")
    assert (project_path / ".titan" / "secrets.env").exists()


# --- scope="env" is gone ---

def test_set_env_scope_removed(mock_env):
    sm = SecretManager()
    with pytest.raises(ValueError, match="Unknown secret scope"):
        sm.set("my_temp_secret", "temp_value", scope="env")
    assert "MY_TEMP_SECRET" not in os.environ


def test_delete_env_scope_removed(mock_env):
    os.environ["TO_DELETE"] = "value"
    sm = SecretManager()
    with pytest.raises(ValueError, match="Unknown secret scope"):
        sm.delete("to_delete", scope="env")
    assert os.environ["TO_DELETE"] == "value"


# --- delete ---

def test_delete_user_scope(mock_keyring):
    sm = SecretManager()
    sm.delete("to_delete", scope="user")
    mock_keyring[2].assert_called_once_with("titan", "to_delete")


def test_delete_project_scope(tmp_project_path, mock_env, mock_keyring):
    mock_keyring[0].return_value = None
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("TO_DELETE='value'\nOTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("to_delete", scope="project")

    content = secrets_file.read_text()
    assert "TO_DELETE" not in content
    assert "OTHER_KEY='other_value'" in content
    # The in-memory copy is gone too, not just the file line.
    assert sm.get("to_delete") is None


def test_delete_project_scope_secret_not_found(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("OTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("non_existent", scope="project")

    assert "OTHER_KEY='other_value'" in secrets_file.read_text()


# --- Lazy namespace migration: reads that miss under a scoped service name
# --- fall back to the legacy ones and move the entry to its new home.

@pytest.fixture
def keyring_store(mock_env):
    store = {}
    with patch('keyring.get_password', side_effect=lambda ns, k: store.get((ns, k))), \
         patch('keyring.set_password', side_effect=lambda ns, k, v: store.__setitem__((ns, k), v)), \
         patch('keyring.delete_password', side_effect=lambda ns, k: store.pop((ns, k), None)):
        yield store


def test_scoped_miss_falls_back_to_legacy_and_copies(keyring_store, tmp_path):
    keyring_store[("titan", "work_api_key")] = "sk-legacy"

    sm = SecretManager(project_path=tmp_path)
    assert sm.get("work_api_key", namespace="titan.core") == "sk-legacy"

    # Copied to the scoped namespace; the legacy copy stays so an installed
    # pre-broker Titan on the same machine keeps working.
    assert keyring_store == {
        ("titan.core", "work_api_key"): "sk-legacy",
        ("titan", "work_api_key"): "sk-legacy",
    }


def test_scoped_hit_wins_over_legacy_copy(keyring_store, tmp_path):
    keyring_store[("titan.core", "k")] = "scoped"
    keyring_store[("titan", "k")] = "stale"

    sm = SecretManager(project_path=tmp_path)
    assert sm.get("k", namespace="titan.core") == "scoped"
    # No migration ran; the stale copy is untouched (delete sweeps it).
    assert keyring_store[("titan", "k")] == "stale"


def test_legacy_namespace_read_does_not_fall_back(keyring_store, tmp_path):
    keyring_store[("ragnarok", "k")] = "value"

    sm = SecretManager(project_path=tmp_path)
    assert sm.get("k", namespace="titan") is None


def test_migration_write_failure_still_returns_value(mock_env, tmp_path):
    def get_password(ns, k):
        return "sk-legacy" if ns == "titan" else None

    with patch('keyring.get_password', side_effect=get_password), \
         patch('keyring.set_password', side_effect=RuntimeError("read-only backend")), \
         patch('keyring.delete_password') as mock_delete:
        sm = SecretManager(project_path=tmp_path)
        assert sm.get("k", namespace="titan.core") == "sk-legacy"
        # The failed write must not delete the only copy.
        mock_delete.assert_not_called()


def test_scoped_delete_sweeps_legacy_namespaces(keyring_store, tmp_path):
    keyring_store[("titan.core", "k")] = "v1"
    keyring_store[("titan", "k")] = "v2"
    keyring_store[("ragnarok", "k")] = "v3"

    sm = SecretManager(project_path=tmp_path)
    sm.delete("k", namespace="titan.core", scope="user")

    assert keyring_store == {}


# --- Fixes from the PR #261 review round ---

def test_legacy_fallback_continues_past_a_failing_namespace(mock_env, tmp_path):
    """One legacy namespace raising must not hide a key stored in the next."""
    def get_password(ns, k):
        if ns == "titan.core":
            return None
        if ns == "titan":
            raise RuntimeError("backend hiccup")
        return "sk-from-ragnarok" if ns == "ragnarok" else None

    with patch('keyring.get_password', side_effect=get_password), \
         patch('keyring.set_password'), \
         patch('keyring.delete_password'):
        sm = SecretManager(project_path=tmp_path)
        assert sm.get("k", namespace="titan.core") == "sk-from-ragnarok"


def test_project_secrets_file_is_owner_only(tmp_project_path, mock_env, mock_keyring):
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("api_token", "tok_value", scope="project")

    mode = (tmp_project_path / ".titan" / "secrets.env").stat().st_mode & 0o777
    assert mode == 0o600


def test_project_secret_round_trip_with_special_characters(tmp_project_path, mock_env, mock_keyring):
    """Quotes, backslashes and newlines must survive set() -> file -> get()."""
    nasty = "it's a \"secret\" with \\slashes\\ and\na newline"
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("nasty_token", nasty, scope="project")

    # A fresh manager re-parses the file from disk (the real read path).
    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("nasty_token") == nasty


def test_project_secret_update_keeps_single_line_entry(tmp_project_path, mock_env, mock_keyring):
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("token", "first", scope="project")
    sm.set("token", "second", scope="project")
    sm.set("other", "x-value", scope="project")

    lines = (tmp_project_path / ".titan" / "secrets.env").read_text().splitlines()
    assert sum(1 for line in lines if line.startswith("TOKEN=")) == 1

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("token") == "second"
    assert fresh.get("other") == "x-value"


# --- Fixes from the PR #261 second review round ---

def test_dollar_sequences_survive_round_trip(tmp_project_path, mock_env, mock_keyring):
    """`${...}` inside a secret is part of the secret, not env interpolation."""
    secret = "p$$w${HOME}x-${UNDEFINED}-end"
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("dollar_token", secret, scope="project")

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("dollar_token") == secret


def test_export_style_entry_can_be_deleted(tmp_project_path, mock_env, mock_keyring):
    """Entries dotenv accepts (export prefix, lowercase) must be deletable."""
    mock_keyring[0].return_value = None
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("export github_token='abc-value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    assert sm.get("github_token") == "abc-value"

    sm.delete("github_token", scope="project")
    assert "github_token" not in secrets_file.read_text()

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("github_token") is None


def test_export_style_entry_updates_in_place(tmp_project_path, mock_env, mock_keyring):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("export api_token='old'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("api_token", "new-value", scope="project")

    lines = [
        line for line in secrets_file.read_text().splitlines() if "API_TOKEN" in line.upper()
    ]
    assert len(lines) == 1

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("api_token") == "new-value"


def test_scoped_keyring_error_still_reaches_legacy_fallback(mock_env, tmp_path):
    """A transient failure on the scoped read must not skip the legacy lookup."""
    def get_password(ns, k):
        if ns == "titan.core":
            raise RuntimeError("backend hiccup")
        return "sk-legacy-copy" if ns == "titan" else None

    with patch('keyring.get_password', side_effect=get_password), \
         patch('keyring.set_password'), \
         patch('keyring.delete_password'):
        sm = SecretManager(project_path=tmp_path)
        assert sm.get("k", namespace="titan.core") == "sk-legacy-copy"


def test_resolve_reports_origin(tmp_project_path, mock_env, mock_keyring):
    os.environ["FROM_ENV"] = "env-value"
    (tmp_project_path / ".titan" / "secrets.env").write_text("FROM_FILE='file-value'\n")
    mock_keyring[0].side_effect = lambda ns, k: "kr-value" if k == "from_keyring" else None

    sm = SecretManager(project_path=tmp_project_path)
    assert sm.resolve("from_env") == ("env-value", "env")
    assert sm.resolve("from_file") == ("file-value", "project")
    assert sm.resolve("from_keyring") == ("kr-value", "keyring")
    assert sm.resolve("missing", namespace="titan") == (None, None)


def test_set_registers_value_for_redaction(tmp_project_path, mock_env, mock_keyring):
    """Store-then-use must redact before any read-back happens."""
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("fresh_token", "just-typed-secret", scope="user")
    assert redaction.redact("echo just-typed-secret") == f"echo {redaction.REDACTED}"


# --- Fixes from the PR #261 third review round ---

def test_append_to_file_without_trailing_newline(tmp_project_path, mock_env, mock_keyring):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text('OTHER="a"')  # no trailing newline

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("new_key", "b-value", scope="project")

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("other") == "a"
    assert fresh.get("new_key") == "b-value"


def test_update_removes_duplicate_definitions(tmp_project_path, mock_env, mock_keyring):
    """dotenv resolves the LAST definition — an update must not leave one behind."""
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("github_token='old1'\nGITHUB_TOKEN='old2'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("github_token", "new-value", scope="project")

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("github_token") == "new-value"
    assert secrets_file.read_text().count("GITHUB_TOKEN") == 1


def test_lowercase_without_export_can_be_deleted(tmp_project_path, mock_env, mock_keyring):
    mock_keyring[0].return_value = None
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("github_token='abc-value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("github_token", scope="project")
    assert "github_token" not in secrets_file.read_text()
    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("github_token") is None


def test_uppercase_with_export_can_be_updated(tmp_project_path, mock_env, mock_keyring):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("export API_TOKEN='old'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("api_token", "new-value", scope="project")

    fresh = SecretManager(project_path=tmp_project_path)
    assert fresh.get("api_token") == "new-value"


def test_scoped_delete_does_not_sweep_legacy_it_never_owned(keyring_store, tmp_path):
    """One plugin's delete must not destroy a legacy copy another plugin
    would migrate — the sweep needs ownership evidence (a scoped copy)."""
    keyring_store[("titan", "github_token")] = "legacy-copy"

    sm = SecretManager(project_path=tmp_path)
    sm.delete("github_token", namespace="titan.plugins.jira", scope="user")

    assert keyring_store == {("titan", "github_token"): "legacy-copy"}


# --- Fixes from the PR #261 fourth review round ---

def test_resolve_priority_when_same_key_everywhere(tmp_project_path, mock_env, mock_keyring):
    os.environ["SHARED"] = "env-wins"
    (tmp_project_path / ".titan" / "secrets.env").write_text("SHARED='from-file'\n")
    mock_keyring[0].return_value = "from-keyring"

    sm = SecretManager(project_path=tmp_project_path)
    assert sm.resolve("shared") == ("env-wins", "env")


def test_vault_stores_blank_values_brokers_are_the_guard(tmp_project_path, mock_env, mock_keyring):
    """Pinned semantics: the vault (inside the boundary) does not validate
    values — the broker's store/prompt paths are where blanks are rejected.
    A blank read back from the keyring is treated as absent."""
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("blank", "   ", scope="user")
    mock_keyring[1].assert_called_once_with("titan", "blank", "   ")

    mock_keyring[0].return_value = ""
    assert sm.get("blank") is None


def test_default_project_path_is_cwd(tmp_path, mock_env, mock_keyring, monkeypatch):
    """The raw vault falls back to cwd; project-root resolution is the
    responsibility of create_broker_factory / the session factories."""
    (tmp_path / ".titan").mkdir()
    (tmp_path / ".titan" / "secrets.env").write_text("CWD_KEY='cwd-value'\n")
    monkeypatch.chdir(tmp_path)

    sm = SecretManager()
    assert sm.project_path == tmp_path
    assert sm.get("cwd_key") == "cwd-value"


def test_delete_project_scope_keeps_memory_if_file_write_fails(tmp_project_path, mock_env, mock_keyring):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("TOKEN='value'\n")
    sm = SecretManager(project_path=tmp_project_path)

    with patch("builtins.open", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            sm.delete("token", scope="project")

    # Memory and file still agree: the secret survives in both.
    assert sm.get("token") == "value"
    assert "TOKEN" in secrets_file.read_text()
