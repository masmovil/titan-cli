# titan_cli/core/plugins/models.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class PluginConfig(BaseModel):
    """
    Represents the configuration for an individual plugin.
    """
    enabled: bool = Field(True, description="Whether the plugin is enabled.")
    config: Dict[str, Any] = Field(default_factory=dict, description="Plugin-specific configuration options.")

class GitPluginConfig(BaseModel):
    """Configuration for Git plugin."""
    main_branch: str = Field("main", description="Main/default branch name")
    default_remote: str = Field("origin", description="Default remote name")
    protected_branches: List[str] = Field(default_factory=lambda: ["main"], description="Protected branches")


class GitHubPluginConfig(BaseModel):
    """Configuration for GitHub plugin."""
    repo_owner: Optional[str] = Field(..., description="GitHub repository owner (user or organization).")
    repo_name: Optional[str] = Field(..., description="GitHub repository name.")
    default_branch: Optional[str] = Field(None, description="Default branch to use (e.g., 'main', 'develop').")
    default_reviewers: List[str] = Field(default_factory=list, description="Default PR reviewers.")
    pr_template_path: Optional[str] = Field(None, description="Path to PR template file within the repository.")
    auto_assign_prs: bool = Field(False, description="Automatically assign PRs to the author.")


class JiraPluginConfig(BaseModel):
    """Configuration for JIRA plugin."""
    base_url: str = Field(..., description="JIRA instance URL (e.g., 'https://jira.company.com')")
    email: str = Field(..., description="User email for authentication")
    # api_token is stored in secrets, not in config.toml
    # It appears in the JSON schema for interactive configuration but is optional in the model
    api_token: Optional[str] = Field(None, description="JIRA API token (Personal Access Token)", json_schema_extra={"format": "password", "required_in_schema": True})
    default_project: str = Field(..., description="Default JIRA project key (e.g., 'ECAPP', 'PROJ')")
    timeout: int = Field(30, description="Request timeout in seconds")
    enable_cache: bool = Field(True, description="Enable caching for API responses")
    cache_ttl: int = Field(300, description="Cache time-to-live in seconds")
