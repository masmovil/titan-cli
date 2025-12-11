# plugins/titan-plugin-github/titan_plugin_github/agents/config_loader.py
"""Configuration loader for PR Agent."""

import tomli
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    # Python 3.9+
    from importlib.resources import files
except ImportError:
    # Python 3.7-3.8 fallback
    from importlib_resources import files

# Import default limits from plugin utils
from ..utils import (
    DEFAULT_MAX_DIFF_SIZE,
    DEFAULT_MAX_FILES_IN_DIFF,
    DEFAULT_MAX_COMMITS_TO_ANALYZE
)


@dataclass
class PRAgentConfig:
    """PR Agent configuration loaded from TOML."""

    name: str
    description: str
    version: str

    # Prompts
    pr_system_prompt: str
    commit_system_prompt: str
    architecture_system_prompt: str

    # Diff analysis limits
    max_diff_size: int
    max_files_in_diff: int
    max_commits_to_analyze: int

    # Features
    enable_template_detection: bool
    enable_dynamic_sizing: bool
    enable_user_confirmation: bool
    enable_fallback_prompts: bool
    enable_debug_output: bool

    # Raw config for custom access
    raw: Dict[str, Any]


def load_agent_config(
    agent_name: str = "pr_agent",
    config_dir: Optional[Path] = None
) -> PRAgentConfig:
    """
    Load agent configuration from TOML file.

    Args:
        agent_name: Name of the agent (e.g., "pr_agent")
        config_dir: Optional custom config directory

    Returns:
        PRAgentConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Determine config file path
    if config_dir:
        config_path = config_dir / f"{agent_name}.toml"
    else:
        # Use importlib.resources for robust path resolution
        # Works with both development and installed (pip/pipx) environments
        config_files = files("titan_plugin_github.config")
        config_file = config_files.joinpath(f"{agent_name}.toml")

        # Convert Traversable to Path
        # In Python 3.9+, this handles both filesystem and zip-based resources
        if hasattr(config_file, "__fspath__"):
            config_path = Path(config_file.__fspath__())
        else:
            # Fallback for older Python or non-filesystem resources
            config_path = Path(str(config_file))

    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    # Load TOML
    with open(config_path, "rb") as f:
        data = tomli.load(f)

    # Extract sections
    agent_meta = data.get("agent", {})
    prompts = data.get("agent", {}).get("prompts", {})
    limits = data.get("agent", {}).get("limits", {})
    features = data.get("agent", {}).get("features", {})

    # Build PRAgentConfig
    return PRAgentConfig(
        name=agent_meta.get("name", agent_name),
        description=agent_meta.get("description", ""),
        version=agent_meta.get("version", "1.0.0"),
        # Prompts
        pr_system_prompt=prompts.get("pr_description", {}).get("system", ""),
        commit_system_prompt=prompts.get("commit_message", {}).get("system", ""),
        architecture_system_prompt=prompts.get("architecture_review", {}).get("system", ""),
        # Limits (use defaults from utils)
        max_diff_size=limits.get("max_diff_size", DEFAULT_MAX_DIFF_SIZE),
        max_files_in_diff=limits.get("max_files_in_diff", DEFAULT_MAX_FILES_IN_DIFF),
        max_commits_to_analyze=limits.get("max_commits_to_analyze", DEFAULT_MAX_COMMITS_TO_ANALYZE),
        # Features
        enable_template_detection=features.get("enable_template_detection", True),
        enable_dynamic_sizing=features.get("enable_dynamic_sizing", True),
        enable_user_confirmation=features.get("enable_user_confirmation", True),
        enable_fallback_prompts=features.get("enable_fallback_prompts", True),
        enable_debug_output=features.get("enable_debug_output", False),
        # Raw for custom access
        raw=data
    )


# Singleton cache to avoid reloading config
_config_cache: Dict[str, PRAgentConfig] = {}


def get_agent_config(agent_name: str = "pr_agent") -> PRAgentConfig:
    """
    Get agent configuration (cached).

    Args:
        agent_name: Name of the agent

    Returns:
        PRAgentConfig instance (cached)
    """
    if agent_name not in _config_cache:
        _config_cache[agent_name] = load_agent_config(agent_name)

    return _config_cache[agent_name]
