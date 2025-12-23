# plugins/titan-plugin-git/titan_plugin_git/plugin.py
import shutil
from typing import Optional
from pathlib import Path
from titan_cli.core.plugins.models import GitPluginConfig
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig # Needed for type hinting
from titan_cli.core.secrets import SecretManager # Needed for type hinting
from .clients.git_client import GitClient
from .exceptions import GitClientError
from .messages import msg
from .steps.status_step import get_git_status_step
from .steps.commit_step import create_git_commit_step
from .steps.prompt_step import prompt_for_commit_message_step
from .steps.push_step import create_git_push_step


class GitPlugin(TitanPlugin):
    """
    Titan CLI Plugin for Git operations.
    Provides a GitClient for interacting with the Git CLI.
    """

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Provides core Git CLI functionalities."

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config: TitanConfig, secrets: SecretManager) -> None:
        """
        Initialize with configuration.
        
        Reads config from:
            config.config.plugins["git"].config
        """

        # Get plugin-specific configuration data
        plugin_config_data = self._get_plugin_config(config)

        # Validate configuration using Pydantic model
        validated_config = GitPluginConfig(**plugin_config_data)

        # Initialize client with validated configuration
        self._client = GitClient(
            main_branch=validated_config.main_branch,
            default_remote=validated_config.default_remote,
            protected_branches=validated_config.protected_branches
        )

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """
        Extract plugin-specific configuration.
        
        Args:
            config: TitanConfig instance
        
        Returns:
            Plugin config dict (empty if not configured)
        """
        if "git" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["git"]
        return plugin_entry.config if hasattr(plugin_entry, 'config') else {}

    def get_config_schema(self) -> dict:
        """
        Return JSON schema for plugin configuration.
        
        Returns:
            JSON schema dict
        """
        from titan_cli.core.plugins.models import GitPluginConfig
        return GitPluginConfig.model_json_schema()


    def is_available(self) -> bool:
        """
        Checks if the Git CLI is installed and available.
        """
        # Leverage the GitClient's own check
        return shutil.which("git") is not None and hasattr(self, '_client') and self._client is not None

    def get_client(self) -> GitClient:
        """
        Returns the initialized GitClient instance.
        """
        if not hasattr(self, '_client') or self._client is None:
            raise GitClientError(msg.Plugin.git_client_not_available)
        return self._client

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        from .steps.branch_steps import get_current_branch_step, get_base_branch_step
        from .steps.ai_commit_message_step import ai_generate_commit_message

        return {
            "get_status": get_git_status_step,
            "create_commit": create_git_commit_step,
            "prompt_for_commit_message": prompt_for_commit_message_step,
            "push": create_git_push_step,
            "get_current_branch": get_current_branch_step,
            "get_base_branch": get_base_branch_step,
            "ai_generate_commit_message": ai_generate_commit_message,
        }

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Returns the path to the workflows directory for this plugin.
        """
        return Path(__file__).parent / "workflows"
