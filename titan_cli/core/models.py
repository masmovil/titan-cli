# core/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict
from .plugins.models import PluginConfig

class ProjectConfig(BaseModel):
    """
    Represents the configuration for a specific project.
    Defined in .titan/config.toml.
    """
    name: str = Field(..., description="Name of the project.")
    type: Optional[str] = Field("generic", description="Type of the project (e.g., 'fullstack', 'backend', 'frontend').")

class AIProviderConfig(BaseModel):
    """Configuración de un provider específico"""
    name: str = Field(..., description="Nombre del provider (ej: 'Corporate Gemini')")
    type: str = Field(..., description="'corporate' o 'individual'")
    provider: str = Field(..., description="'anthropic', 'gemini', 'openai'")
    model: Optional[str] = Field(None, description="Modelo a usar")
    base_url: Optional[str] = Field(None, description="URL custom (solo corporate)")
    max_tokens: int = Field(4096)
    temperature: float = Field(0.7)

class AIConfig(BaseModel):
    """
    Represents the configuration for AI provider integration.
    Can be defined globally or per project.
    """
    default: str = Field("default", description="ID del provider por defecto")
    providers: Dict[str, AIProviderConfig] = Field(default_factory=dict)

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
