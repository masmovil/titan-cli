# core/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ProjectConfig(BaseModel):
    """
    Represents the configuration for a specific project.
    Defined in .titan/config.toml.
    """
    name: str = Field(..., description="Name of the project.")
    type: Optional[str] = Field("generic", description="Type of the project (e.g., 'fullstack', 'backend', 'frontend').")

class AIConfig(BaseModel):
    """
    Represents the configuration for AI provider integration.
    Can be defined globally or per project.
    """
    provider: str = Field("anthropic", description="AI provider to use (e.g., 'anthropic', 'openai', 'gemini').")
    model: Optional[str] = Field(None, description="Specific AI model to use (e.g., 'claude-3-haiku-20240307').")
    api_key: Optional[str] = Field(None, description="API key for the AI provider (typically loaded from secrets).")

class PluginConfig(BaseModel):
    """
    Represents the configuration for an individual plugin.
    """
    enabled: bool = Field(True, description="Whether the plugin is enabled.")
    config: Dict[str, Any] = Field(default_factory=dict, description="Plugin-specific configuration options.")

class CoreConfig(BaseModel):
    """
    Represents core Titan CLI settings, typically defined in the global config.
    """
    project_root: Optional[str] = Field(None, description="Absolute path to the root directory containing all user projects.")

class TitanConfigModel(BaseModel):
    """
    The main Pydantic model for the entire Titan CLI configuration.
    This model validates the merged configuration from global and project sources.
    """
    project: Optional[ProjectConfig] = Field(None, description="Project-specific configuration.")
    core: Optional[CoreConfig] = Field(None, description="Core Titan CLI settings.")
    ai: Optional[AIConfig] = Field(None, description="AI provider configuration.")
    plugins: Dict[str, PluginConfig] = Field(default_factory=dict, description="Dictionary of plugin configurations.")
