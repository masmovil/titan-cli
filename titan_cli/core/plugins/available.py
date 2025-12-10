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

# This list should be updated when new official plugins are published.
KNOWN_PLUGINS: List[KnownPlugin] = [
    {
        "name": "git",
        "description": "Provides core Git functionalities for workflows.",
        "package_name": "titan-plugin-git"
    },
    {
        "name": "github",
        "description": "Adds GitHub integration for pull requests and more.",
        "package_name": "titan-plugin-github"
    },
]
