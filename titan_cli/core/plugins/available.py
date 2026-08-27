"""Registry of known plugins available to Titan CLI."""

from typing import List, Optional, TypedDict


class KnownPlugin(TypedDict):
    """Represents a known plugin that can be installed."""
    name: str
    description: str
    package_name: str
    dependencies: List[str]
    source: str
    repo_url: Optional[str]
    recommended_ref: Optional[str]


# This list should be updated when new official or curated community plugins
# are published.
KNOWN_PLUGINS: List[KnownPlugin] = [
    {
        "name": "git",
        "description": "Provides core Git functionalities for workflows.",
        "package_name": "titan-plugin-git",
        "dependencies": [],
        "source": "official",
        "repo_url": None,
        "recommended_ref": None,
    },
    {
        "name": "github",
        "description": "Adds GitHub integration for pull requests and more.",
        "package_name": "titan-plugin-github",
        "dependencies": ["git"],
        "source": "official",
        "repo_url": None,
        "recommended_ref": None,
    },
    {
        "name": "jira",
        "description": "JIRA integration for issue management.",
        "package_name": "titan-plugin-jira",
        "dependencies": [],
        "source": "official",
        "repo_url": None,
        "recommended_ref": None,
    },
    {
        "name": "ragnarok",
        "description": "Ragnarok Android and iOS workflow plugin.",
        "package_name": "titan-plugin-ragnarok",
        "dependencies": [],
        "source": "community",
        "repo_url": "https://github.com/masmovil/ragnarok-titan-cli-workflows",
        "recommended_ref": "0.7.0",
    },
    {
        "name": "slack",
        "description": "Slack integration for personal messaging and workspace access.",
        "package_name": "titan-plugin-slack",
        "dependencies": []
    },
]
