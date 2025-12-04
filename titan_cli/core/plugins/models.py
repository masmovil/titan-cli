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
