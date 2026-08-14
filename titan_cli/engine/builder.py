"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""
from __future__ import annotations

from typing import Optional, Any

from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.models import AIConfig
from titan_cli.core.security import create_ai_provider, create_broker_factory
from .context import WorkflowContext
from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.ai.router import AIExecutor


class WorkflowContextBuilder:
    """
    Fluent builder for WorkflowContext.

    Example:
        plugin_registry = PluginRegistry()
        ai_config = AIConfig(
            default_connection="default",
            connections={
                "default": {
                    "name": "Default OpenAI",
                    "connection_type": "direct_provider",
                    "provider": "openai",
                    "default_model": "gpt-5",
                }
            },
        )
        ctx = WorkflowContextBuilder(plugin_registry, ai_config=ai_config) \\
            .with_ai() \\
            .with_ai_router() \\
            .build()
    """

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        ai_config: Optional[AIConfig] = None
    ):
        """
        Initialize builder.

        Args:
            plugin_registry: The PluginRegistry instance.
            ai_config: Optional AI configuration.
        """
        self._plugin_registry = plugin_registry
        self._ai_config = ai_config

        # Service clients
        self._ai = None
        self._ai_router = None
        self._titan_config = None
        self._git = None
        self._github = None
        self._jira = None
        self._slack = None

        # Plugin managers (keyed by plugin name)
        self._plugin_managers: dict = {}

    def with_ai(self, ai_client: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add AI client.

        Args:
            ai_client: Optional AIClient instance (auto-created if None)
        """
        if ai_client:
            # DI pure
            self._ai = ai_client
        else:
            # Convenience - auto-create from ai_config
            if self._ai_config:
                try:
                    self._ai = AIClient(self._ai_config, create_ai_provider)
                except AIConfigurationError:
                    self._ai = None
            else:
                self._ai = None
        return self

    def with_ai_router(self, ai_router: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add the AI execution façade steps route their AI calls through.

        Args:
            ai_router: Optional AIExecutor instance (auto-created if None)

        Note:
            `ctx.ai` stays available and unchanged for steps that talk to a
            remote connection directly; `ctx.ai_router` is what honors the
            user's per-task provider preference.
        """
        if ai_router:
            self._ai_router = ai_router
        else:
            self._ai_router = AIExecutor(
                self._ai_config,
                provider_factory=create_ai_provider,
                secret_broker=create_broker_factory().for_plugin("core"),
            )
        return self

    def with_titan_config(self, titan_config: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add the TitanConfig instance, for steps that need to persist user
        preferences (e.g. `upsert_task_ai_preference`).

        Args:
            titan_config: The TitanConfig instance in scope at the call site.
                There is no auto-create path - TitanConfig requires a
                PluginRegistry/project root already resolved elsewhere.
        """
        self._titan_config = titan_config
        return self

    def with_git(self, git_client: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add Git client.

        Args:
            git_client: Optional GitClient instance (auto-created if None)
        """
        if git_client:
            self._git = git_client
        else:
            # Auto-create from plugin registry
            git_plugin = self._plugin_registry.get_plugin("git")
            if git_plugin and git_plugin.is_available():
                try:
                    self._git = git_plugin.get_client()
                except Exception: # Catch any exception during client retrieval
                    self._git = None # Fail silently
            else:
                self._git = None
        return self

    def with_github(self, github_client: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add GitHub client.

        Args:
            github_client: Optional GitHubClient instance (auto-loaded if None)
        """
        if github_client:
            self._github = github_client
        else:
            # Auto-create from plugin registry
            github_plugin = self._plugin_registry.get_plugin("github")
            if github_plugin and github_plugin.is_available():
                try:
                    self._github = github_plugin.get_client()
                except Exception: # Catch any exception during client retrieval
                    self._github = None # Fail silently
            else:
                self._github = None
        return self

    def with_plugin_managers(self, plugin_name: str, managers: Any) -> WorkflowContextBuilder:
        """
        Register workflow managers for a plugin.

        Args:
            plugin_name: Plugin identifier (e.g. "github", "jira")
            managers: Plugin-specific managers container
        """
        self._plugin_managers[plugin_name] = managers
        return self

    def with_jira(self, jira_client: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add JIRA client to workflow context.

        The JIRA client is optional and only used by JIRA plugin steps.
        Other plugin steps will have ctx.jira = None and should ignore it.

        Args:
            jira_client: Optional JiraClient instance (auto-loaded if None).
                        If None, attempts to load from JIRA plugin registry.
                        If plugin is not available or fails to load, sets ctx.jira = None.

        Returns:
            Self for method chaining

        Note:
            Steps from other plugins do not need to handle ctx.jira.
            Only JIRA plugin steps should check for and use ctx.jira.
        """
        if jira_client:
            self._jira = jira_client
        else:
            # Auto-create from plugin registry
            jira_plugin = self._plugin_registry.get_plugin("jira")
            if jira_plugin and jira_plugin.is_available():
                try:
                    self._jira = jira_plugin.get_client()
                except Exception: # Catch any exception during client retrieval
                    self._jira = None # Fail silently
            else:
                self._jira = None
        return self

    def with_slack(self, slack_client: Optional[Any] = None) -> WorkflowContextBuilder:
        """
        Add Slack client to workflow context.

        The Slack client is optional and only used by Slack plugin steps.
        Other plugin steps will have ctx.slack = None and should ignore it.

        Args:
            slack_client: Optional SlackClient instance (auto-loaded if None).
                         If plugin is not available or fails to load, sets ctx.slack = None.

        Returns:
            Self for method chaining
        """
        if slack_client:
            self._slack = slack_client
        else:
            slack_plugin = self._plugin_registry.get_plugin("slack")
            if slack_plugin and slack_plugin.is_available():
                try:
                    self._slack = slack_plugin.get_client()
                except Exception:
                    self._slack = None
            else:
                self._slack = None
        return self


    def build(self) -> WorkflowContext:
        """Build the WorkflowContext."""
        return WorkflowContext(
            plugin_manager=self._plugin_registry,
            titan_config=self._titan_config,
            ai=self._ai,
            ai_router=self._ai_router,
            git=self._git,
            github=self._github,
            github_managers=self._plugin_managers.get("github"),
            jira=self._jira,
            slack=self._slack,
        )
