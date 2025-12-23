# plugins/titan-plugin-jira/titan_plugin_jira/agents/config_loader.py
"""Configuration loader for JIRA Agent."""

import tomli
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

try:
    # Python 3.9+
    from importlib.resources import files
except ImportError:
    # Python 3.7-3.8 fallback
    from importlib_resources import files


class JiraAgentConfig(BaseModel):
    """JIRA Agent configuration loaded from TOML."""

    name: str = Field(..., description="Agent name")
    description: str = Field("", description="Agent description")
    version: str = Field("1.0.0", description="Agent version")

    # Prompts
    requirements_system_prompt: str = Field("", description="System prompt for requirements analysis")
    description_enhancement_prompt: str = Field("", description="System prompt for description enhancement")
    comment_generation_prompt: str = Field("", description="System prompt for comment generation")
    subtask_suggestion_prompt: str = Field("", description="System prompt for subtask suggestion")
    smart_labeling_prompt: str = Field("", description="System prompt for smart labeling")

    # Limits
    max_description_length: int = Field(5000, ge=0, description="Maximum description length")
    max_subtasks: int = Field(10, ge=1, description="Maximum subtasks to suggest")
    max_comments_to_analyze: int = Field(20, ge=1, description="Maximum comments to analyze")
    max_linked_issues: int = Field(15, ge=1, description="Maximum linked issues to consider")

    # AI Parameters
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="AI temperature for generation")
    max_tokens: int = Field(2000, ge=1, description="Maximum tokens per AI request")

    # Features
    enable_requirement_extraction: bool = Field(True, description="Enable requirement extraction")
    enable_subtasks: bool = Field(True, description="Enable subtask suggestion")
    enable_subtask_suggestion: bool = Field(True, description="Enable subtask suggestion (legacy)")
    enable_risk_analysis: bool = Field(True, description="Enable risk analysis")
    enable_dependency_detection: bool = Field(True, description="Enable dependency detection")
    enable_acceptance_criteria: bool = Field(True, description="Enable acceptance criteria generation")
    enable_gherkin_tests: bool = Field(False, description="Enable Gherkin/BDD test scenario generation")
    enable_strict_labeling: bool = Field(False, description="Enable strict label classification")
    enable_token_saving: bool = Field(False, description="Enable token optimization strategies")
    enable_debug_output: bool = Field(False, description="Enable debug output")

    # Formatting
    template: str = Field("", description="Optional Jinja2 template filename for formatting output")

    # Raw config for custom access
    raw: Dict[str, Any] = Field(default_factory=dict, description="Raw TOML data")

    model_config = ConfigDict(frozen=False)  # Allow mutation for caching


def load_agent_config(
    agent_name: str = "jira_agent",
    config_dir: Optional[Path] = None
) -> JiraAgentConfig:
    """
    Load agent configuration from TOML file.

    Args:
        agent_name: Name of the agent (e.g., "jira_agent")
        config_dir: Optional custom config directory

    Returns:
        JiraAgentConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Determine config file path
    if config_dir:
        config_path = config_dir / f"{agent_name}.toml"
    else:
        # Use importlib.resources for robust path resolution
        config_files = files("titan_plugin_jira.config")
        config_file = config_files.joinpath(f"{agent_name}.toml")

        # Convert Traversable to Path
        if hasattr(config_file, "__fspath__"):
            config_path = Path(config_file.__fspath__())
        else:
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
    formatting = data.get("agent", {}).get("formatting", {})

    # Build JiraAgentConfig
    return JiraAgentConfig(
        name=agent_meta.get("name", agent_name),
        description=agent_meta.get("description", ""),
        version=agent_meta.get("version", "1.0.0"),
        # Prompts
        requirements_system_prompt=prompts.get("requirements_analysis", {}).get("system", ""),
        description_enhancement_prompt=prompts.get("description_enhancement", {}).get("system", ""),
        comment_generation_prompt=prompts.get("comment_generation", {}).get("system", ""),
        subtask_suggestion_prompt=prompts.get("subtask_suggestion", {}).get("system", ""),
        smart_labeling_prompt=prompts.get("smart_labeling", {}).get("system", ""),
        # Limits
        max_description_length=limits.get("max_description_length", 5000),
        max_subtasks=limits.get("max_subtasks", 10),
        max_comments_to_analyze=limits.get("max_comments_to_analyze", 20),
        max_linked_issues=limits.get("max_linked_issues", 15),
        # AI Parameters
        temperature=limits.get("temperature", agent_meta.get("temperature", 0.7)),
        max_tokens=limits.get("max_tokens", agent_meta.get("max_tokens", 2000)),
        # Features (support both enable_subtasks and enable_subtask_suggestion)
        enable_requirement_extraction=features.get("enable_requirement_extraction", True),
        enable_subtasks=features.get("enable_subtasks", features.get("enable_subtask_suggestion", True)),
        enable_subtask_suggestion=features.get("enable_subtask_suggestion", features.get("enable_subtasks", True)),
        enable_risk_analysis=features.get("enable_risk_analysis", True),
        enable_dependency_detection=features.get("enable_dependency_detection", True),
        enable_acceptance_criteria=features.get("enable_acceptance_criteria", True),
        enable_gherkin_tests=features.get("enable_gherkin_tests", False),
        enable_strict_labeling=features.get("enable_strict_labeling", False),
        enable_token_saving=features.get("enable_token_saving", False),
        enable_debug_output=features.get("enable_debug_output", False),
        # Formatting
        template=formatting.get("template", ""),
        # Raw for custom access
        raw=data
    )
