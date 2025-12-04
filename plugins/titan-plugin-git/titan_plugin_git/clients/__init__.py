# plugins/titan-plugin-git/titan_plugin_git/clients/__init__.py
"""
Git client module
"""

from .git_client import GitClient, GitClientError

__all__ = ["GitClient", "GitClientError"]
