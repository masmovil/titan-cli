"""Plugin trust classification and static security scan (sec-011)."""

from pathlib import Path

import pytest

from titan_cli.core.models import SecurityConfig, TitanConfigModel
from titan_cli.core.plugins.community_sources import PluginChannel
from titan_cli.core.plugins.trust import (
    PluginTrust,
    classify_plugin,
    scan_plugin_source,
)


# --- Classification -------------------------------------------------------

def test_official_plugin_from_entry_point():
    assert classify_plugin("git", channel=None) == PluginTrust.OFFICIAL
    assert classify_plugin("github", channel=None) == PluginTrust.OFFICIAL


def test_unknown_entry_point_plugin_is_community():
    assert classify_plugin("shady-helper", channel=None) == PluginTrust.COMMUNITY


def test_stable_channel_is_community_even_for_official_names():
    assert classify_plugin("git", channel=PluginChannel.STABLE) == PluginTrust.COMMUNITY


def test_dev_local_channel_is_local():
    assert classify_plugin("ragnarok", channel=PluginChannel.DEV_LOCAL) == PluginTrust.LOCAL


# --- Static scan ----------------------------------------------------------

def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_clean_source_has_no_findings(tmp_path):
    _write(tmp_path, "plugin/steps.py", "from titan_cli.engine import Success\n")
    assert scan_plugin_source(tmp_path) == []


def test_keyring_import_flagged(tmp_path):
    _write(tmp_path, "plugin/sneaky.py", "import keyring\n")
    findings = scan_plugin_source(tmp_path)
    assert len(findings) == 1
    assert findings[0].code == "keyring-import"
    assert findings[0].file == "plugin/sneaky.py"
    assert findings[0].line == 1


def test_keyring_from_import_flagged(tmp_path):
    _write(tmp_path, "a.py", "from keyring import get_password\n")
    assert scan_plugin_source(tmp_path)[0].code == "keyring-import"


def test_keyring_submodule_import_flagged(tmp_path):
    _write(tmp_path, "a.py", "import keyring.backends.SecretService\n")
    assert scan_plugin_source(tmp_path)[0].code == "keyring-import"


def test_vault_import_flagged(tmp_path):
    _write(tmp_path, "a.py", "from titan_cli.core.security._vault import SecretManager\n")
    codes = {f.code for f in scan_plugin_source(tmp_path)}
    assert "vault-import" in codes
    assert "secret-manager" in codes


def test_secret_manager_reference_flagged(tmp_path):
    _write(tmp_path, "a.py", "def f(x):\n    return SecretManager()\n")
    findings = scan_plugin_source(tmp_path)
    assert findings[0].code == "secret-manager"
    assert findings[0].line == 2


def test_secret_manager_attribute_flagged(tmp_path):
    _write(tmp_path, "a.py", "import titan_cli\nm = titan_cli.core.security._vault.SecretManager\n")
    codes = {f.code for f in scan_plugin_source(tmp_path)}
    assert "secret-manager" in codes


def test_tests_directory_skipped(tmp_path):
    _write(tmp_path, "tests/test_x.py", "import keyring\n")
    assert scan_plugin_source(tmp_path) == []


def test_unparseable_file_is_reported_not_hidden(tmp_path):
    _write(tmp_path, "broken.py", "def f(:\n")
    findings = scan_plugin_source(tmp_path)
    assert len(findings) == 1
    assert findings[0].code == "unparseable"


# --- [security] config ----------------------------------------------------

def test_security_config_defaults_to_in_process():
    assert SecurityConfig().community_plugins == "in_process"
    assert TitanConfigModel().security is None


def test_security_config_rejects_unknown_isolation_model():
    with pytest.raises(Exception):
        SecurityConfig(community_plugins="yolo")


def test_titan_config_parses_security_section():
    model = TitanConfigModel(security={"community_plugins": "in_process"})
    assert model.security.community_plugins == "in_process"
