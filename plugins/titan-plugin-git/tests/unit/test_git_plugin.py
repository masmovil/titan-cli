from pathlib import Path
from unittest.mock import MagicMock, patch

from titan_plugin_git.plugin import GitPlugin


def test_git_plugin_initializes_client_with_project_root():
    config = MagicMock()
    config.project_root = Path("/tmp/titan-project")
    config.config.plugins = {}

    plugin = GitPlugin()

    with patch("titan_plugin_git.plugin.GitClient") as git_client_cls:
        plugin.initialize(config, MagicMock())

    git_client_cls.assert_called_once_with(
        repo_path="/tmp/titan-project",
        main_branch="main",
        default_remote="origin",
    )
