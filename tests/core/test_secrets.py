import pytest
from unittest.mock import patch
import os
import threading
import time

from titan_cli.core.secrets import SecretManager


# Fixture for a temporary project path
@pytest.fixture
def tmp_project_path(tmp_path):
    (tmp_path / ".titan").mkdir()
    return tmp_path


# Fixture for mocking os.environ
@pytest.fixture
def mock_env():
    with patch.dict(os.environ, clear=True):
        yield


# Fixture for mocking keyring
@pytest.fixture
def mock_keyring():
    with (
        patch("keyring.get_password") as mock_get,
        patch("keyring.set_password") as mock_set,
        patch("keyring.delete_password") as mock_delete,
    ):
        yield mock_get, mock_set, mock_delete


# Fixture for mocking dotenv
@pytest.fixture
def mock_dotenv():
    with patch("titan_cli.core.secrets.load_dotenv") as mock_load:
        yield mock_load


# --- Test SecretManager initialization and project secret loading ---
def test_secret_manager_init_loads_project_secrets(tmp_project_path, mock_dotenv):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.touch()
    SecretManager(project_path=tmp_project_path)
    mock_dotenv.assert_called_once_with(secrets_file)


def test_secret_manager_init_no_project_secrets_file(tmp_project_path, mock_dotenv):
    SecretManager(project_path=tmp_project_path)
    mock_dotenv.assert_not_called()


# --- Test get method ---
def test_get_from_env(mock_env, mock_keyring):
    os.environ["MY_ENV_SECRET"] = "env_value"
    sm = SecretManager()
    assert sm.get("my_env_secret") == "env_value"
    mock_keyring[0].assert_not_called()  # keyring.get_password


def test_get_from_keyring(mock_env, mock_keyring):
    mock_keyring[0].return_value = "keyring_value"
    sm = SecretManager()
    assert sm.get("my_keyring_secret") == "keyring_value"
    mock_keyring[0].assert_called_once_with("titan", "my_keyring_secret")


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


def test_get_with_scope_identifies_project_secret(
    tmp_project_path,
    mock_env,
    mock_keyring,
):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='project_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    resolved = sm.get_with_scope("project_token")

    assert resolved is not None
    assert resolved.value == "project_value"
    assert resolved.scope == "project"
    mock_keyring[0].assert_not_called()


def test_get_with_scope_keeps_real_env_over_project_secret(
    tmp_project_path,
    mock_env,
):
    os.environ["PROJECT_TOKEN"] = "env_value"
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='project_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    resolved = sm.get_with_scope("project_token")

    assert resolved is not None
    assert resolved.value == "env_value"
    assert resolved.scope == "env"


def test_get_with_scope_keeps_real_env_when_value_matches_project_secret(
    tmp_project_path,
    mock_env,
):
    os.environ["PROJECT_TOKEN"] = "same_value"
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='same_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    resolved = sm.get_with_scope("project_token")

    assert resolved is not None
    assert resolved.value == "same_value"
    assert resolved.scope == "env"


def test_get_with_scope_keeps_runtime_env_override_after_project_injection(
    tmp_project_path,
    mock_env,
):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='project_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    assert os.environ["PROJECT_TOKEN"] == "project_value"

    os.environ["PROJECT_TOKEN"] = "cli_value"
    resolved = sm.get_with_scope("project_token")

    assert os.environ["PROJECT_TOKEN"] == "cli_value"
    assert resolved is not None
    assert resolved.value == "cli_value"
    assert resolved.scope == "env"


def test_get_from_scope_reads_exact_scope(
    tmp_project_path,
    mock_env,
    mock_keyring,
):
    os.environ["PROJECT_TOKEN"] = "env_value"
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='project_value'\n")
    mock_keyring[0].return_value = "user_value"

    sm = SecretManager(project_path=tmp_project_path)

    assert sm.get_from_scope("project_token", scope="env") == "env_value"
    assert sm.get_from_scope("project_token", scope="project") == "project_value"
    assert sm.get_from_scope("project_token", scope="user") == "user_value"


def test_project_scope_updates_process_env_when_it_mirrors_project(
    tmp_project_path,
    mock_env,
):
    sm = SecretManager(project_path=tmp_project_path)

    sm.set("project_token", "old_value", scope="project")
    sm.set("project_token", "new_value", scope="project")

    assert os.environ["PROJECT_TOKEN"] == "new_value"
    resolved = sm.get_with_scope("project_token")
    assert resolved is not None
    assert resolved.value == "new_value"
    assert resolved.scope == "project"


def test_project_scope_updates_stay_coherent_across_instances(
    tmp_project_path,
    mock_env,
):
    first = SecretManager(project_path=tmp_project_path)
    second = SecretManager(project_path=tmp_project_path)

    first.set("project_token", "first_value", scope="project")
    second.set("project_token", "final_value", scope="project")

    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    assert "PROJECT_TOKEN='final_value'" in secrets_file.read_text()
    assert os.environ["PROJECT_TOKEN"] == "final_value"

    first_resolved = first.get_with_scope("project_token")
    second_resolved = second.get_with_scope("project_token")

    assert first_resolved is not None
    assert first_resolved.value == "final_value"
    assert first_resolved.scope == "project"
    assert second_resolved is not None
    assert second_resolved.value == "final_value"
    assert second_resolved.scope == "project"


def test_project_env_injection_does_not_leak_between_projects(
    tmp_path,
    mock_env,
):
    first_project = tmp_path / "first"
    second_project = tmp_path / "second"
    (first_project / ".titan").mkdir(parents=True)
    (second_project / ".titan").mkdir(parents=True)
    (first_project / ".titan" / "secrets.env").write_text(
        "SHARED_TOKEN='first_value'\n"
    )
    (second_project / ".titan" / "secrets.env").write_text(
        "SHARED_TOKEN='second_value'\n"
    )

    first = SecretManager(project_path=first_project)
    assert os.environ["SHARED_TOKEN"] == "first_value"
    second = SecretManager(project_path=second_project)

    first_resolved = first.get_with_scope("shared_token")
    second_resolved = second.get_with_scope("shared_token")

    assert first_resolved is not None
    assert first_resolved.value == "first_value"
    assert first_resolved.scope == "project"
    assert second_resolved is not None
    assert second_resolved.value == "second_value"
    assert second_resolved.scope == "project"


def test_project_scope_update_does_not_make_other_project_read_wrong_secret(
    tmp_path,
    mock_env,
):
    first_project = tmp_path / "first"
    second_project = tmp_path / "second"
    (first_project / ".titan").mkdir(parents=True)
    (second_project / ".titan").mkdir(parents=True)
    (first_project / ".titan" / "secrets.env").write_text(
        "SHARED_TOKEN='first_value'\n"
    )
    (second_project / ".titan" / "secrets.env").write_text(
        "SHARED_TOKEN='second_value'\n"
    )

    first = SecretManager(project_path=first_project)
    second = SecretManager(project_path=second_project)

    second.set("shared_token", "second_updated", scope="project")
    first_resolved = first.get_with_scope("shared_token")
    second_resolved = second.get_with_scope("shared_token")

    assert os.environ["SHARED_TOKEN"] == "second_updated"
    assert first_resolved is not None
    assert first_resolved.value == "first_value"
    assert first_resolved.scope == "project"
    assert second_resolved is not None
    assert second_resolved.value == "second_updated"
    assert second_resolved.scope == "project"


def test_project_scope_writes_are_serialized_across_instances(
    tmp_project_path,
    mock_env,
    monkeypatch,
):
    first = SecretManager(project_path=tmp_project_path)
    second = SecretManager(project_path=tmp_project_path)
    first_write_entered = threading.Event()
    release_first_write = threading.Event()
    second_write_started = threading.Event()
    errors: list[BaseException] = []
    original_write = SecretManager._write_project_secret_lines_atomic

    def delayed_first_write(self, secrets_file, lines):
        if (
            not first_write_entered.is_set()
            and any(line.startswith("FIRST_TOKEN=") for line in lines)
        ):
            first_write_entered.set()
            release_first_write.wait(timeout=2)
        return original_write(self, secrets_file, lines)

    def record_errors(action):
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(
        SecretManager,
        "_write_project_secret_lines_atomic",
        delayed_first_write,
    )

    first_thread = threading.Thread(
        target=lambda: record_errors(
            lambda: first.set("first_token", "first_value", scope="project"),
        ),
    )
    first_thread.start()
    assert first_write_entered.wait(timeout=2)

    def write_second_secret():
        second_write_started.set()
        second.set("second_token", "second_value", scope="project")

    second_thread = threading.Thread(
        target=lambda: record_errors(write_second_secret),
    )
    second_thread.start()
    assert second_write_started.wait(timeout=2)
    time.sleep(0.05)
    assert second_thread.is_alive()
    release_first_write.set()

    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []

    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    content = secrets_file.read_text()
    assert "FIRST_TOKEN='first_value'" in content
    assert "SECOND_TOKEN='second_value'" in content


def test_project_scope_does_not_update_real_env_even_when_values_match(
    tmp_project_path,
    mock_env,
):
    os.environ["PROJECT_TOKEN"] = "same_value"
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='same_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("project_token", "new_project_value", scope="project")

    assert os.environ["PROJECT_TOKEN"] == "same_value"
    resolved = sm.get_with_scope("project_token")
    assert resolved is not None
    assert resolved.value == "same_value"
    assert resolved.scope == "env"


def test_project_scope_update_keeps_runtime_env_override_after_project_injection(
    tmp_project_path,
    mock_env,
):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='project_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    assert os.environ["PROJECT_TOKEN"] == "project_value"

    os.environ["PROJECT_TOKEN"] = "cli_value"
    sm.set("project_token", "new_project_value", scope="project")

    assert os.environ["PROJECT_TOKEN"] == "cli_value"
    assert "PROJECT_TOKEN='new_project_value'" in secrets_file.read_text()
    resolved = sm.get_with_scope("project_token")
    assert resolved is not None
    assert resolved.value == "cli_value"
    assert resolved.scope == "env"


def test_project_scope_delete_clears_process_env_when_it_mirrors_project(
    tmp_project_path,
    mock_env,
):
    sm = SecretManager(project_path=tmp_project_path)

    sm.set("project_token", "project_value", scope="project")
    sm.delete("project_token", scope="project")

    assert "PROJECT_TOKEN" not in os.environ


def test_project_scope_delete_keeps_real_env_even_when_values_match(
    tmp_project_path,
    mock_env,
):
    os.environ["PROJECT_TOKEN"] = "same_value"
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("PROJECT_TOKEN='same_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("project_token", scope="project")

    assert os.environ["PROJECT_TOKEN"] == "same_value"
    assert sm.get_with_scope("project_token").scope == "env"


# --- Test set method ---
def test_set_env_scope(mock_env):
    sm = SecretManager()
    sm.set("my_temp_secret", "temp_value", scope="env")
    assert os.environ["MY_TEMP_SECRET"] == "temp_value"


def test_set_user_scope(mock_keyring):
    sm = SecretManager()
    sm.set("my_user_secret", "user_value", scope="user")
    mock_keyring[1].assert_called_once_with("titan", "my_user_secret", "user_value")


def test_set_user_scope_raises_when_keyring_write_fails(mock_keyring, tmp_project_path):
    mock_keyring[1].side_effect = RuntimeError("keyring unavailable")
    sm = SecretManager(project_path=tmp_project_path)

    with pytest.raises(RuntimeError, match="keyring unavailable"):
        sm.set("my_user_secret", "user_value", scope="user")

    assert not (tmp_project_path / ".titan" / "secrets.env").exists()


def test_set_project_scope_new_secret(tmp_project_path, mock_env):
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("my_project_secret", "project_value", scope="project")

    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    assert secrets_file.exists()
    with open(secrets_file, "r") as f:
        content = f.read()
    assert "MY_PROJECT_SECRET='project_value'" in content


def test_set_project_scope_update_secret(tmp_project_path, mock_env):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("EXISTING_SECRET='old_value'\nOTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.set("existing_secret", "new_value", scope="project")

    with open(secrets_file, "r") as f:
        content = f.read()
    assert "EXISTING_SECRET='new_value'" in content
    assert "OTHER_KEY='other_value'" in content
    assert "EXISTING_SECRET='old_value'" not in content


def test_set_project_scope_creates_dir_if_not_exists(tmp_path, mock_env):
    project_path = tmp_path / "new_project"
    sm = SecretManager(project_path=project_path)
    sm.set("new_secret", "value", scope="project")
    assert (project_path / ".titan" / "secrets.env").exists()


# --- Test delete method ---
def test_delete_env_scope(mock_env):
    os.environ["TO_DELETE"] = "value"
    sm = SecretManager()
    sm.delete("to_delete", scope="env")
    assert "TO_DELETE" not in os.environ


def test_delete_user_scope(mock_keyring):
    sm = SecretManager()
    sm.delete("to_delete", scope="user")
    mock_keyring[2].assert_called_once_with("titan", "to_delete")


def test_delete_project_scope(tmp_project_path, mock_env):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("TO_DELETE='value'\nOTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("to_delete", scope="project")

    with open(secrets_file, "r") as f:
        content = f.read()
    assert "TO_DELETE" not in content
    assert "OTHER_KEY='other_value'" in content


def test_delete_project_scope_secret_not_found(tmp_project_path, mock_env):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("OTHER_KEY='other_value'\n")

    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("non_existent", scope="project")

    with open(secrets_file, "r") as f:
        content = f.read()
    assert "OTHER_KEY='other_value'" in content  # Content should be unchanged
