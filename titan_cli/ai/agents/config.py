# titan_cli/ai/agents/config.py
"""Configuration loader for AI Agents."""

import tomli
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Agent configuration loaded from TOML."""

    name: str
    description: str
    version: str

    # Prompts
    pr_system_prompt: str
    commit_system_prompt: str
    architecture_system_prompt: str

    # Limits
    small_pr_max_chars: int
    small_pr_max_tokens: int
    medium_pr_max_chars: int
    medium_pr_max_tokens: int
    large_pr_max_chars: int
    large_pr_max_tokens: int
    very_large_pr_max_chars: int
    very_large_pr_max_tokens: int

    max_diff_size: int
    max_files_in_diff: int
    max_commits_to_analyze: int

    # Behavior
    temperature: float
    max_tokens: int

    # Features
    enable_template_detection: bool
    enable_dynamic_sizing: bool
    enable_user_confirmation: bool
    enable_fallback_prompts: bool
    enable_debug_output: bool

    # Raw config for custom access
    raw: Dict[str, Any]


def load_agent_config(
    agent_name: str = "platform_agent",
    config_dir: Optional[Path] = None
) -> AgentConfig:
    """
    Load agent configuration from TOML file.

    Args:
        agent_name: Name of the agent (e.g., "platform_agent")
        config_dir: Optional custom config directory

    Returns:
        AgentConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Determine config file path
    if config_dir:
        config_path = config_dir / f"{agent_name}.toml"
    else:
        # Default to project config/agents directory
        project_root = Path(__file__).parent.parent.parent.parent
        config_path = project_root / "config" / "agents" / f"{agent_name}.toml"

    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    # Load TOML
    with open(config_path, "rb") as f:
        data = tomli.load(f)

    # Extract sections
    agent_meta = data.get("agent", {})
    prompts = data.get("agent", {}).get("prompts", {})
    limits = data.get("agent", {}).get("limits", {})
    behavior = data.get("agent", {}).get("behavior", {})
    features = data.get("agent", {}).get("features", {})

    # Build AgentConfig
    return AgentConfig(
        name=agent_meta.get("name", agent_name),
        description=agent_meta.get("description", ""),
        version=agent_meta.get("version", "1.0.0"),
        # Prompts
        pr_system_prompt=prompts.get("pr_description", {}).get("system", ""),
        commit_system_prompt=prompts.get("commit_message", {}).get("system", ""),
        architecture_system_prompt=prompts.get("architecture_review", {}).get("system", ""),
        # Limits
        small_pr_max_chars=limits.get("small_pr_max_chars", 500),
        small_pr_max_tokens=limits.get("small_pr_max_tokens", 575),
        medium_pr_max_chars=limits.get("medium_pr_max_chars", 1200),
        medium_pr_max_tokens=limits.get("medium_pr_max_tokens", 1100),
        large_pr_max_chars=limits.get("large_pr_max_chars", 2000),
        large_pr_max_tokens=limits.get("large_pr_max_tokens", 1700),
        very_large_pr_max_chars=limits.get("very_large_pr_max_chars", 3000),
        very_large_pr_max_tokens=limits.get("very_large_pr_max_tokens", 2450),
        max_diff_size=limits.get("max_diff_size", 8000),
        max_files_in_diff=limits.get("max_files_in_diff", 50),
        max_commits_to_analyze=limits.get("max_commits_to_analyze", 15),
        # Behavior
        temperature=behavior.get("temperature", 0.7),
        max_tokens=behavior.get("max_tokens", 4000),
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
_config_cache: Dict[str, AgentConfig] = {}


def get_agent_config(agent_name: str = "platform_agent") -> AgentConfig:
    """
    Get agent configuration (cached).

    Args:
        agent_name: Name of the agent

    Returns:
        AgentConfig instance (cached)
    """
    if agent_name not in _config_cache:
        _config_cache[agent_name] = load_agent_config(agent_name)

    return _config_cache[agent_name]
