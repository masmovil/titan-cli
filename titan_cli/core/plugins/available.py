"""
This file contains a list of known, installable plugins for Titan CLI.

This acts as a centralized registry for the `install` command, so the CLI
knows what plugins are available to be installed via `pipx inject`.
"""
from typing import TypedDict, List

class KnownPlugin(TypedDict):
    """Represents a known plugin that can be installed."""
    name: str
    description: str
    package_name: str
    dependencies: List[str]  # Plugin names that must be installed first

# This list should be updated when new official plugins are published.
KNOWN_PLUGINS: List[KnownPlugin] = [
    {
        "name": "git",
        "description": "Provides core Git functionalities for workflows.",
        "package_name": "titan-plugin-git",
        "dependencies": []
    },
    {
        "name": "github",
        "description": "Adds GitHub integration for pull requests and more.",
        "package_name": "titan-plugin-github",
        "dependencies": ["git"]  # Requires git plugin
    },
    {
        "name": "jira",
        "description": "JIRA integration for issue management.",
        "package_name": "titan-plugin-jira",
        "dependencies": []
    },
]
