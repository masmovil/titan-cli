from pathlib import Path
from typing import Optional, TypedDict, List
from pydantic import ValidationError
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.core.plugins.models import JiraPluginConfig
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig
from titan_cli.core.security import SecretBroker
from .clients.jira_client import JiraClient
from .exceptions import JiraConfigurationError, JiraClientError
from .messages import msg


class TokenValidationResult(TypedDict):
    """Result of token validation."""
    valid: bool
    error: Optional[str]
    user: Optional[str]
    email: Optional[str]
    token_source: dict
    warnings: List[str]


class JiraPlugin(TitanPlugin):
    """
    Titan CLI Plugin for JIRA operations.
    Provides a JiraClient for interacting with JIRA REST API.
    """

    @property
    def titan_requires(self) -> str:
        # Must stay in sync with the titan-cli dependency in this plugin's
        # pyproject.toml; a repo test enforces the pairing.
        return ">=0.8.0"

    @property
    def name(self) -> str:
        return "jira"

    @property
    def description(self) -> str:
        return "Provides JIRA API integration with AI-powered issue management."

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config: TitanConfig, broker: SecretBroker) -> None:
        """
        Initialize with configuration.

        Configuration cascade (project overrides global):
            1. Global credentials (~/.titan/config.toml): base_url, email
            2. Project settings (.titan/config.toml): default_project (optional)

        Note: TitanConfig automatically merges global and project configs,
        so _get_plugin_config() returns the already-merged configuration.

        Resolves the API token key by existence (never reading a value):
            project-specific → jira_api_token → JIRA_API_TOKEN (env) →
            {email}_jira_api_token
        """
        # Get plugin-specific configuration data (already merged by TitanConfig)
        plugin_config_data = self._get_plugin_config(config)

        # Validate configuration using Pydantic model
        # Pydantic validators will check base_url and email during construction
        try:
            validated_config = JiraPluginConfig(**plugin_config_data)
        except ValidationError as e:
            raise JiraConfigurationError(str(e)) from e

        project_name = config.get_project_name()
        token_key, token_source = self._resolve_token_key(
            broker, project_name, validated_config.email
        )

        if not token_key:
            raise JiraConfigurationError(
                "JIRA API token not found in secrets. "
                "Please configure the JIRA plugin to set the API token."
            )

        # The token crosses into the client constructor inside the broker
        # call; the plugin never holds the value.
        self._client = broker.create_client(
            token_key,
            lambda api_token: JiraClient(
                base_url=validated_config.base_url,
                email=validated_config.email,
                api_token=api_token,
                project_key=validated_config.default_project,
                timeout=validated_config.timeout,
                enable_cache=validated_config.enable_cache,
                cache_ttl=validated_config.cache_ttl,
            ),
        )

        # Token source info for diagnostics (the key that resolved, no value)
        self._token_source = token_source

    def _resolve_token_key(
        self, broker: SecretBroker, project_name: Optional[str], email: str
    ) -> tuple[Optional[str], dict]:
        """
        Pick the first token key that resolves, by existence only.

        Priority: project-specific → global → email-specific. Each key
        resolves through the broker's full cascade (env var `JIRA_API_TOKEN`
        already satisfies the `jira_api_token` candidate — a separate
        env-var candidate would be dead code), and the reported source
        reflects the LEVEL that actually resolved it, not the candidate's
        label: an env-provided token must show up as "environment", not as
        a stored global token.

        Returns:
            (key, source_info) — key is None when nothing resolves; source_info
            describes where the token comes from, for diagnostics (no value).
        """
        candidates = []
        if project_name:
            candidates.append((
                f"{project_name}_jira_api_token",
                {"type": "project-specific", "details": f"Token for project '{project_name}'"},
            ))
        candidates.extend([
            ("jira_api_token",
             {"type": "global", "details": "Global JIRA token (recommended)"}),
            (f"{email}_jira_api_token",
             {"type": "email-specific", "details": f"Token for email '{email}'"}),
        ])

        for key, source in candidates:
            origin = broker.source(key)
            if origin is None:
                continue
            if origin == "env":
                source = {"type": "environment",
                          "details": f"Environment variable {key.upper()}"}
            elif origin == "project":
                source = {"type": "project-secrets",
                          "details": "Project .titan/secrets.env"}
            else:
                # Keyring: the candidate's label already says which KEY was
                # picked; make the storage level explicit too, so the user
                # never reads a scope label as a storage location.
                source = {**source, "details": f"{source['details']} (system keyring)"}
            return key, {"name": key, **source}

        return None, {
            "name": "unknown",
            "type": "unknown",
            "details": "Token source could not be identified",
        }

    @property
    def has_default_project(self) -> bool:
        """Check if a default project is configured."""
        return hasattr(self, '_client') and self._client.project_key is not None

    def validate_token(self) -> TokenValidationResult:
        """
        Validate that the current token works by making a test API call.

        Also checks configuration completeness and returns warnings.

        Returns:
            TokenValidationResult with validation results
        """
        warnings = []

        # Check if default project is configured
        if not self.has_default_project:
            warnings.append(
                "No default_project configured. "
                "Some operations (like create_subtask) will fail without a project."
            )

        if not self.is_available():
            return {
                "valid": False,
                "error": "JIRA client not initialized",
                "user": None,
                "email": None,
                "token_source": getattr(self, '_token_source', {}),
                "warnings": warnings
            }

        myself_result = self._client.get_current_user()

        match myself_result:
            case ClientSuccess(data=user):
                return {
                    "valid": True,
                    "error": None,
                    "user": user.display_name,
                    "email": user.email,
                    "token_source": getattr(self, '_token_source', {}),
                    "warnings": warnings
                }
            case ClientError(error_message=err):
                return {
                    "valid": False,
                    "error": err,
                    "user": None,
                    "email": None,
                    "token_source": getattr(self, '_token_source', {}),
                    "warnings": warnings
                }

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

        Technical fields (timeout, enable_cache, cache_ttl) are excluded from the wizard
        since they have sensible defaults and most users don't need to change them.

        Returns:
            JSON schema dict with api_token marked as required (even though it's stored in secrets)
        """
        schema = JiraPluginConfig.model_json_schema()

        # Exclude technical fields from wizard (they have good defaults)
        # Users can still manually edit config.toml if needed
        technical_fields = ["timeout", "enable_cache", "cache_ttl"]
        for field in technical_fields:
            schema.get("properties", {}).pop(field, None)
            if field in schema.get("required", []):
                schema["required"].remove(field)

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
        # Original steps
        from .steps.search_saved_query_step import search_saved_query_step
        from .steps.search_jql_step import search_jql_step
        from .steps.prompt_select_issue_step import prompt_select_issue_step
        from .steps.get_issue_step import get_issue_step
        from .steps.get_comments_step import get_comments_step
        from .steps.select_jira_issue_step import select_jira_issue_step
        from .steps.build_jira_task_context_step import build_jira_task_context_step
        from .steps.confirm_and_assign_issue_step import confirm_and_assign_issue
        from .steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step
        from .steps.list_versions_step import list_versions_step
        from .steps.issue_management_steps import (
            get_transitions_step,
            transition_issue_step,
            verify_issue_state_step,
            create_version_step,
            ensure_version_exists_step,
            assign_fix_version_step,
            verify_issue_has_fix_version_step,
        )

        # Generic Issue Creation Workflow steps
        from .steps.prompt_issue_description_step import prompt_issue_description
        from .steps.select_issue_type_step import select_issue_type
        from .steps.select_issue_priority_step import select_issue_priority
        from .steps.ai_enhance_issue_description_step import ai_enhance_issue_description
        from .steps.review_issue_description_step import review_issue_description
        from .steps.confirm_assignee_for_new_issue_step import confirm_assignee_for_new_issue
        from .steps.create_generic_issue_step import create_generic_issue

        return {
            # Original steps
            "search_saved_query": search_saved_query_step,
            "search_jql": search_jql_step,
            "prompt_select_issue": prompt_select_issue_step,
            "get_issue": get_issue_step,
            "get_comments": get_comments_step,
            "select_jira_issue": select_jira_issue_step,
            "build_jira_task_context": build_jira_task_context_step,
            "confirm_and_assign_issue": confirm_and_assign_issue,
            "ai_analyze_issue_requirements": ai_analyze_issue_requirements_step,
            "list_versions": list_versions_step,
            "get_transitions": get_transitions_step,
            "transition_issue": transition_issue_step,
            "verify_issue_state": verify_issue_state_step,
            "create_version": create_version_step,
            "ensure_version_exists": ensure_version_exists_step,
            "assign_fix_version": assign_fix_version_step,
            "verify_issue_has_fix_version": verify_issue_has_fix_version_step,

            # Generic Issue Creation Workflow steps
            "prompt_issue_description": prompt_issue_description,
            "select_issue_type": select_issue_type,
            "select_issue_priority": select_issue_priority,
            "ai_enhance_issue_description": ai_enhance_issue_description,
            "review_issue_description": review_issue_description,
            "confirm_assignee_for_new_issue": confirm_assignee_for_new_issue,
            "create_generic_issue": create_generic_issue,
        }

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Returns the path to the workflows directory.

        Returns:
            Path to workflows directory containing YAML workflow definitions
        """
        return Path(__file__).parent / "workflows"
