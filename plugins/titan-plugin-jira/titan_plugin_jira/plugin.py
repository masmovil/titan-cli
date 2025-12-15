from pathlib import Path
from typing import Optional
from titan_cli.core.plugins.models import JiraPluginConfig
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from .clients.jira_client import JiraClient
from .exceptions import JiraConfigurationError, JiraClientError
from .messages import msg


class JiraPlugin(TitanPlugin):
    """
    Titan CLI Plugin for JIRA operations.
    Provides a JiraClient for interacting with JIRA REST API.
    """

    @property
    def name(self) -> str:
        return "jira"

    @property
    def description(self) -> str:
        return "Provides JIRA API integration with AI-powered issue management."

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config: TitanConfig, secrets: SecretManager) -> None:
        """
        Initialize with configuration.

        Reads config from:
            config.config.plugins["jira"].config

        Reads API token from secrets:
            JIRA_API_TOKEN or {email}_jira_api_token
        """
        # Get plugin-specific configuration data
        plugin_config_data = self._get_plugin_config(config)

        # Validate configuration using Pydantic model
        validated_config = JiraPluginConfig(**plugin_config_data)

        # Get API token from secrets
        # Try multiple secret keys for backwards compatibility
        # Priority: project-specific → plugin-specific → env var → email-specific
        project_name = config.get_active_project()
        project_key = f"{project_name}_jira_api_token" if project_name else None

        api_token = (
            (secrets.get(project_key) if project_key else None) or  # Project-specific keychain
            secrets.get("jira_api_token") or  # Standard: plugin_fieldname
            secrets.get("JIRA_API_TOKEN") or  # Environment variable
            secrets.get(f"{validated_config.email}_jira_api_token")  # Email-specific
        )

        if not api_token:
            raise JiraConfigurationError(
                "JIRA API token not found in secrets. "
                "Please configure the JIRA plugin to set the API token."
            )

        # Initialize client with validated configuration
        self._client = JiraClient(
            base_url=validated_config.base_url,
            email=validated_config.email,
            api_token=api_token,
            project_key=validated_config.default_project,
            timeout=validated_config.timeout,
            enable_cache=validated_config.enable_cache,
            cache_ttl=validated_config.cache_ttl
        )

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """
        Extract plugin-specific configuration.

        Args:
            config: TitanConfig instance

        Returns:
            Plugin config dict (empty if not configured)
        """
        if "jira" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["jira"]
        return plugin_entry.config if hasattr(plugin_entry, 'config') else {}

    def get_config_schema(self) -> dict:
        """
        Return JSON schema for plugin configuration.

        Returns:
            JSON schema dict with api_token marked as required (even though it's stored in secrets)
        """
        schema = JiraPluginConfig.model_json_schema()
        # Ensure api_token is in required list for interactive configuration
        # (even though it's Optional in the model since it's stored in secrets)
        if "api_token" not in schema.get("required", []):
            schema.setdefault("required", []).append("api_token")
        return schema

    def is_available(self) -> bool:
        """
        Checks if the JIRA client is initialized and ready.
        """
        return hasattr(self, '_client') and self._client is not None

    def get_client(self) -> JiraClient:
        """
        Returns the initialized JiraClient instance.
        """
        if not hasattr(self, '_client') or self._client is None:
            raise JiraClientError(msg.Plugin.JIRA_CLIENT_NOT_AVAILABLE)
        return self._client

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        from .steps.search_saved_query_step import search_saved_query_step
        from .steps.prompt_select_issue_step import prompt_select_issue_step
        from .steps.get_issue_step import get_issue_step
        from .steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step
        return {
            "search_saved_query": search_saved_query_step,
            "prompt_select_issue": prompt_select_issue_step,
            "get_issue": get_issue_step,
            "ai_analyze_issue_requirements": ai_analyze_issue_requirements_step,
        }

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Returns the path to the workflows directory.

        Returns:
            Path to workflows directory containing YAML workflow definitions
        """
        return Path(__file__).parent / "workflows"
