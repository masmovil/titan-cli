# plugins/titan-plugin-github/titan_plugin_github/agents/config_loader.py
"""Configuration loader for PR Agent."""

import tomli
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

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


class PRAgentConfig(BaseModel):
    """PR Agent configuration loaded from TOML."""

    name: str = Field(..., description="Agent name")
    description: str = Field("", description="Agent description")
    version: str = Field("1.0.0", description="Agent version")

    # Prompts
    pr_system_prompt: str = Field("", description="System prompt for PR generation")
    commit_system_prompt: str = Field("", description="System prompt for commit messages")
    architecture_system_prompt: str = Field("", description="System prompt for architecture review")

    # Diff analysis limits
    max_diff_size: int = Field(DEFAULT_MAX_DIFF_SIZE, ge=0, description="Maximum diff size to analyze")
    max_files_in_diff: int = Field(DEFAULT_MAX_FILES_IN_DIFF, ge=1, description="Maximum files in diff")
    max_commits_to_analyze: int = Field(DEFAULT_MAX_COMMITS_TO_ANALYZE, ge=1, description="Maximum commits to analyze")

    # Features
    enable_template_detection: bool = Field(True, description="Enable PR template detection")
    enable_dynamic_sizing: bool = Field(True, description="Enable dynamic PR sizing")
    enable_user_confirmation: bool = Field(True, description="Enable user confirmation")
    enable_fallback_prompts: bool = Field(True, description="Enable fallback prompts")
    enable_debug_output: bool = Field(False, description="Enable debug output")

    # Raw config for custom access
    raw: Dict[str, Any] = Field(default_factory=dict, description="Raw TOML data")


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
    try:
        with open(config_path, "rb") as f:
            data = tomli.load(f)
    except tomli.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read config {config_path}: {e}")

    # Validate config structure
    if "agent" not in data:
        raise ValueError(f"Missing [agent] section in {config_path}")

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
