# core/models/__init__.py
from enum import StrEnum
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ..plugins.models import PluginConfig


class ProjectConfig(BaseModel):
    """
    Represents the configuration for a specific project.
    Defined in .titan/config.toml.
    """

    name: str = Field(..., description="Name of the project.")
    type: Optional[str] = Field(
        "generic",
        description="Type of the project (e.g., 'fullstack', 'backend', 'frontend').",
    )


class AIConnectionType(StrEnum):
    """Kinds of AI connections supported by Titan."""

    GATEWAY = "gateway"
    DIRECT_PROVIDER = "direct_provider"


class AIGatewayBackend(StrEnum):
    """Gateway backends supported by Titan."""

    OPENAI_COMPATIBLE = "openai_compatible"


class AIDirectProvider(StrEnum):
    """Direct providers supported by Titan."""

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"


class AIConnectionConfig(BaseModel):
    """Configuration for an AI connection."""

    name: str = Field(..., description="Human-readable connection name")
    connection_type: AIConnectionType = Field(..., description="Connection type")
    gateway_backend: Optional[AIGatewayBackend] = Field(
        None, description="Gateway backend"
    )
    provider: Optional[AIDirectProvider] = Field(
        None, description="Direct provider type"
    )
    base_url: Optional[str] = Field(None, description="Gateway endpoint URL")
    default_model: Optional[str] = Field(
        None, description="Default model to use for this connection"
    )
    max_tokens: int = Field(4096)
    temperature: float = Field(0.7)

    @model_validator(mode="after")
    def validate_shape(self) -> "AIConnectionConfig":
        """Validate mutually exclusive connection settings."""
        if self.connection_type == AIConnectionType.GATEWAY:
            if not self.gateway_backend:
                raise ValueError("gateway connections require 'gateway_backend'")
            if not self.base_url:
                raise ValueError("gateway connections require 'base_url'")
            if self.provider is not None:
                raise ValueError("gateway connections must not define 'provider'")

        if self.connection_type == AIConnectionType.DIRECT_PROVIDER:
            if not self.provider:
                raise ValueError("direct_provider connections require 'provider'")
            if self.gateway_backend is not None:
                raise ValueError(
                    "direct_provider connections must not define 'gateway_backend'"
                )

        return self

    @property
    def model(self) -> Optional[str]:
        """Backward-compatible alias used by older callers."""
        return self.default_model


AIProviderConfig = AIConnectionConfig


class AIConfig(BaseModel):
    """
    Represents the configuration for AI connections.
    Can be defined globally or per project.
    """

    default_connection: Optional[str] = Field(
        None, description="Default AI connection ID"
    )
    default_cli: Optional[str] = Field(
        None,
        description="Default CLI name, used for both headless and interactive CLI work",
    )
    connections: Dict[str, AIConnectionConfig] = Field(default_factory=dict)

    # Neither default is validated against what exists. A default pointing at something that
    # is gone - a connection renamed by hand, a CLI uninstalled - is a real problem, but it is
    # not a reason to refuse to load: rejecting the config here makes the application
    # unstartable, and the only screen that could repair the value is inside it. Both are
    # instead reported at resolution time, by name, with the app running and the config screen
    # reachable. (For `default_cli` there is a second reason: the set of known CLIs lives in
    # `titan_cli.external_cli`, which sits above this module in the dependency graph.)

    @property
    def default(self) -> Optional[str]:
        """Backward-compatible alias used by older callers."""
        return self.default_connection

    @property
    def providers(self) -> Dict[str, AIConnectionConfig]:
        """Backward-compatible alias used by older callers."""
        return self.connections

    preferences: Optional["AIPreferences"] = Field(
        None, description="Persisted routing preferences, one per AI task"
    )


class AIProviderPreference(BaseModel):
    """
    A persisted choice of which KIND of provider to use for an AI task.

    Only the provider type is stored. Which connection or which CLI serves it is a single
    global choice (`AIConfig.default_connection` / `AIConfig.default_cli`), so changing the
    default in one place changes every task that uses that kind of provider.
    """

    provider: str = Field(..., description="AIProviderType value, e.g. 'remote', 'cli_headless'")


class AIPreferences(BaseModel):
    """
    Persisted AI routing preferences, keyed by task.

    The task is the only scope: one choice per kind of work, applied wherever
    that work happens.
    """

    tasks: Dict[str, AIProviderPreference] = Field(default_factory=dict)


AIConfig.model_rebuild()


class SecurityConfig(BaseModel):
    """
    Security posture for third-party plugin execution.

    `community_plugins` names the isolation model community plugins run
    under. Only "in_process" exists today; "worker" and "sandbox" are the
    planned future values — declaring the key now means existing configs
    already state their posture explicitly when those land. An unknown
    value fails validation loudly rather than silently running in-process.
    """

    community_plugins: Literal["in_process"] = Field(
        "in_process",
        description="Isolation model for community plugins (future: worker | sandbox).",
    )


class TitanConfigModel(BaseModel):
    """
    The main Pydantic model for the entire Titan CLI configuration.
    This model validates the merged configuration from global and project sources.
    """

    config_version: str = Field("1.0", description="Configuration schema version.")
    project: Optional[ProjectConfig] = Field(
        None, description="Project-specific configuration."
    )
    ai: Optional[AIConfig] = Field(None, description="AI connection configuration.")
    plugins: Dict[str, PluginConfig] = Field(
        default_factory=dict, description="Dictionary of plugin configurations."
    )
    security: Optional[SecurityConfig] = Field(
        None, description="Security posture for third-party plugin execution."
    )
