import pytest
from unittest.mock import patch, MagicMock
import os

from titan_cli.core.secrets import SecretManager

# Fixture for a temporary project path
@pytest.fixture
def tmp_project_path(tmp_path):
    (tmp_path / ".titan").mkdir()
    return tmp_path

# Fixture for mocking UI components (TextRenderer, PromptsRenderer)
@pytest.fixture
def mock_ui_components():
    with patch('titan_cli.core.secrets.TextRenderer') as mock_text, \
         patch('titan_cli.core.secrets.PromptsRenderer') as mock_prompts:
        mock_prompts_instance = MagicMock()
        mock_prompts.return_value = mock_prompts_instance
        yield mock_text.return_value, mock_prompts_instance

# Fixture for mocking os.environ
@pytest.fixture
def mock_env():
    with patch.dict(os.environ, clear=True):
        yield

# Fixture for mocking keyring
@pytest.fixture
def mock_keyring():
    with patch('keyring.get_password') as mock_get, \
         patch('keyring.set_password') as mock_set, \
         patch('keyring.delete_password') as mock_delete:
        yield mock_get, mock_set, mock_delete

# Fixture for mocking dotenv
@pytest.fixture
def mock_dotenv():
    with patch('titan_cli.core.secrets.load_dotenv') as mock_load:
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
    mock_keyring[0].assert_not_called() # keyring.get_password

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

# --- Test set method ---
def test_set_env_scope(mock_env):
    sm = SecretManager()
    sm.set("my_temp_secret", "temp_value", scope="env")
    assert os.environ["MY_TEMP_SECRET"] == "temp_value"

def test_set_user_scope(mock_keyring):
    sm = SecretManager()
    sm.set("my_user_secret", "user_value", scope="user")
    mock_keyring[1].assert_called_once_with("titan", "my_user_secret", "user_value")

def test_set_project_scope_new_secret(tmp_project_path):
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("my_project_secret", "project_value", scope="project")
    
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    assert secrets_file.exists()
    with open(secrets_file, "r") as f:
        content = f.read()
    assert "MY_PROJECT_SECRET='project_value'" in content

def test_set_project_scope_update_secret(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("EXISTING_SECRET='old_value'\nOTHER_KEY='other_value'\n")
    
    sm = SecretManager(project_path=tmp_project_path)
    sm.set("existing_secret", "new_value", scope="project")
    
    with open(secrets_file, "r") as f:
        content = f.read()
    assert "EXISTING_SECRET='new_value'" in content
    assert "OTHER_KEY='other_value'" in content
    assert "EXISTING_SECRET='old_value'" not in content

def test_set_project_scope_creates_dir_if_not_exists(tmp_path):
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

def test_delete_project_scope(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("TO_DELETE='value'\nOTHER_KEY='other_value'\n")
    
    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("to_delete", scope="project")
    
    with open(secrets_file, "r") as f:
        content = f.read()
    assert "TO_DELETE" not in content
    assert "OTHER_KEY='other_value'" in content

def test_delete_project_scope_secret_not_found(tmp_project_path):
    secrets_file = tmp_project_path / ".titan" / "secrets.env"
    secrets_file.write_text("OTHER_KEY='other_value'\n")
    
    sm = SecretManager(project_path=tmp_project_path)
    sm.delete("non_existent", scope="project")
    
    with open(secrets_file, "r") as f:
        content = f.read()
    assert "OTHER_KEY='other_value'" in content # Content should be unchanged

from titan_cli.messages import msg

# --- Test prompt_and_set method ---
def test_prompt_and_set_success(mock_ui_components, mock_keyring):
    mock_text, mock_prompts = mock_ui_components
    mock_prompts.ask_text.return_value = "my-secret-value"
    
    sm = SecretManager()
    value = sm.prompt_and_set("test_key", "Enter secret:", scope="user")
    
    assert value == "my-secret-value"
    mock_prompts.ask_text.assert_called_once_with("Enter secret:", password=True)
    mock_keyring[1].assert_called_once_with("titan", "test_key", "my-secret-value")
    mock_text.success.assert_called_once_with(msg.Projects.SECRET_SAVED.format(key="test_key", scope="user"))

def test_prompt_and_set_cancelled(mock_ui_components, mock_keyring):
    mock_text, mock_prompts = mock_ui_components
    mock_prompts.ask_text.side_effect = KeyboardInterrupt # Simulate cancellation
    
    sm = SecretManager()
    value = sm.prompt_and_set("test_key", "Enter secret:", scope="user")
    
    assert value is None
    mock_keyring[1].assert_not_called()
    mock_text.warning.assert_called_once_with(msg.Secrets.AI_SETUP_CANCELLED)
