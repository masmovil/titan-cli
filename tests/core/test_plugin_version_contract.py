"""
The official plugins' version contract, enforced at the repo level.

Each official plugin declares its version once (``__version__`` in its
package) and the titan-cli requirement once in its plugin class
(``titan_requires``). Both have counterparts in the plugin's pyproject.toml —
the artifact the installer channels read — and the two sources drift silently
unless something compares them. This test is that something.
"""

import importlib
from pathlib import Path

import pytest

from titan_cli.core.plugins.community_sources import parse_plugin_metadata

REPO_ROOT = Path(__file__).resolve().parents[2]

# The official set. poeditor is excluded on purpose: its package layout is
# broken (the plugin module does not import) and it is not part of the
# official plugins.
OFFICIAL_PLUGINS = ["git", "github", "jira", "slack", "docker"]


def _plugin_parts(name: str):
    pyproject = REPO_ROOT / "plugins" / f"titan-plugin-{name}" / "pyproject.toml"
    metadata = parse_plugin_metadata(pyproject.read_text(encoding="utf-8"))
    assert not metadata["parse_error"], f"unparseable {pyproject}"

    entry_point = metadata["titan_entry_points"][name]
    module_name, _, class_name = entry_point.partition(":")
    plugin_class = getattr(importlib.import_module(module_name), class_name)
    package = importlib.import_module(module_name.split(".", 1)[0])
    return metadata, plugin_class(), package


@pytest.mark.parametrize("name", OFFICIAL_PLUGINS)
def test_package_version_matches_pyproject(name):
    metadata, plugin, package = _plugin_parts(name)
    assert getattr(package, "__version__", None) == metadata["version"], (
        f"titan_plugin_{name}.__version__ and its pyproject version disagree"
    )
    # The plugin instance reports the package version (base-class default).
    assert plugin.version == metadata["version"]


@pytest.mark.parametrize("name", OFFICIAL_PLUGINS)
def test_titan_requires_matches_pyproject_dependency(name):
    metadata, plugin, _ = _plugin_parts(name)
    assert plugin.titan_requires == metadata["titan_requirement"], (
        f"{name}'s titan_requires and its pyproject titan-cli bound disagree"
    )
