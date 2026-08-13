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
    assert "MY_PROJECT_SECRET='project_value'" in secrets_file.read_text()


def test_set_project_scope_update_secret(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("EXISTING_SECRET='old_value'\nOTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("existing_secret", "new_value", scope="project")

    content = secrets_file.read_text()
    assert "EXISTING_SECRET='new_value'" in content
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
