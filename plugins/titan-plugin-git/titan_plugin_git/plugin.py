# plugins/titan-plugin-git/titan_plugin_git/plugin.py
import shutil
from titan_cli.core.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig # Needed for type hinting
from titan_cli.core.secrets import SecretManager # Needed for type hinting
from .clients.git_client import GitClient, GitClientError


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
        Initializes the GitClient.
        """
        try:
            # We assume the project_path in GitClient should be the current working directory
            # or could be derived from config.get_project_root() if we want to tie it to Titan projects.
            # For now, let's just use current working directory as Git operations are context-sensitive.
            self._client = GitClient()
        except GitClientError as e:
            # If Git CLI is not installed, the plugin cannot be initialized
            # We don't re-raise, as initialize() should ideally not fail the whole app startup.
            # is_available() will handle user feedback for missing CLI.
            self._client = None
            print(f"Warning: GitPlugin could not initialize GitClient: {e}")


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
            raise GitClientError("GitPlugin not initialized or Git CLI not available.")
        return self._client

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        from .steps.status_step import get_git_status_step
        from .steps.commit_step import create_git_commit_step
        return {
            "get_status": get_git_status_step,
            "create_commit": create_git_commit_step,
        }
