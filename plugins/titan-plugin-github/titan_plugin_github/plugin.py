# plugins/titan-plugin-github/titan_plugin_github/plugin.py
from typing import Type
from pydantic import BaseModel
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.core.plugins.models import GitHubPluginConfig
from .clients.github_client import GitHubClient
from .steps.create_pr_step import create_pr_step
from .steps.review_pr_step import review_pr_step, analyze_pr_security_step, analyze_pr_performance_step
from .clients.github_client import GitHubError
from .utils import detect_github_repo

class GitHubPlugin(TitanPlugin):
    """
    Titan CLI Plugin for GitHub operations.
    """

    @property
    def name(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return "Provides GitHub integration for PRs, issues, and more."

    @property
    def dependencies(self) -> list[str]:
        return ["git"]

    def initialize(self, config: TitanConfig, secrets: SecretManager) -> None:
        """
        Initializes the GitHubClient.
        """
        # Get plugin-specific configuration data
        plugin_config_data = self._get_plugin_config(config)

        # Validate configuration using Pydantic model
        validated_config = GitHubPluginConfig(**plugin_config_data)

        repo_owner = validated_config.repo_owner
        repo_name = validated_config.repo_name

        # Attempt to auto-detect if not explicitly configured
        if not repo_owner or not repo_name:
            detected_owner, detected_name = detect_github_repo()
            if detected_owner and detected_name:
                repo_owner = repo_owner or detected_owner
                repo_name = repo_name or detected_name
        
        # If still missing, raise an error
        if not repo_owner or not repo_name:
            raise GitHubConfigurationError(msg.GitHub.CONFIG_REPO_MISSING)

        # Get the git client from the registry
        git_plugin = config.registry.get_plugin("git")
        if not git_plugin or not git_plugin.is_available():
            raise GitHubError("The 'git' plugin is a required dependency and is not available.")
        git_client = git_plugin.get_client()

        # Initialize client with validated configuration and git_client
        self._client = GitHubClient(
            config=validated_config,
            secrets=secrets,
            git_client=git_client,
            repo_owner=repo_owner, # Pass detected/configured owner
            repo_name=repo_name # Pass detected/configured name
        )

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """
        Extract plugin-specific configuration.
        
        Args:
            config: TitanConfig instance
        
        Returns:
            Plugin config dict (empty if not configured)
        """
        if "github" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["github"]
        return plugin_entry.config if hasattr(plugin_entry, 'config') else {}

    def get_config_schema(self) -> dict:
        """Returns the JSON schema for the plugin's configuration."""
        return GitHubPluginConfig.model_json_schema()

    def is_available(self) -> bool:
        """
        Checks if the GitHub CLI is installed and available.
        """
        import shutil
        return shutil.which("gh") is not None and hasattr(self, '_client') and self._client is not None

    def get_client(self) -> GitHubClient:
        """
        Returns the initialized GitHubClient instance.
        """
        # Ensure the client is initialized, potentially adding a check here
        if not hasattr(self, '_client') or self._client is None:
            raise GitHubError("GitHubPlugin not initialized. GitHub client may not be available.")
        return self._client

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        return {
            "create_pr": create_pr_step,
            "review_pr": review_pr_step,
            "analyze_pr_security": analyze_pr_security_step,
            "analyze_pr_performance": analyze_pr_performance_step,
        }
