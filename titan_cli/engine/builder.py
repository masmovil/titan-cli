"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""
from __future__ import annotations

from typing import Optional, Any

from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.models import AIConfig
from titan_cli.core.secrets import SecretManager
from .context import WorkflowContext
from .ui_container import UIComponents
from .views_container import UIViews


class WorkflowContextBuilder:
    """
    Fluent builder for WorkflowContext.

    Example:
        plugin_registry = PluginRegistry()
        secrets = SecretManager()
        ai_config = AIConfig(provider="anthropic", model="claude-3-haiku-20240307")
        ctx = WorkflowContextBuilder(plugin_registry, secrets, ai_config) \\
            .with_ui() \\
            .with_ai() \\
            .build()
    """

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        secrets: SecretManager,
        ai_config: Optional[AIConfig] = None
    ):
        """
        Initialize builder.

        Args:
            plugin_registry: The PluginRegistry instance.
            secrets: The SecretManager instance.
            ai_config: Optional AI configuration.
        """
        self._plugin_registry = plugin_registry
        self._secrets = secrets
        self._ai_config = ai_config

        # UI containers
        self._ui: Optional[UIComponents] = None
        self._views: Optional[UIViews] = None

        # Service clients
        self._ai = None
        self._git = None
        self._github = None

    def with_ui(
        self,
        ui: Optional[UIComponents] = None,
        views: Optional[UIViews] = None
    ) -> "WorkflowContextBuilder":
        """
        Add UI components and views.
        
        Args:
            ui: Optional UIComponents (auto-created if None)
            views: Optional UIViews (auto-created if None)
        
        Returns:
            Builder instance
        """
        # Create or inject UIComponents
        self._ui = ui or UIComponents.create()

        # Create or inject UIViews
        self._views = views or UIViews.create(self._ui)

        return self

    def with_ai(self, ai_client: Optional[Any] = None) -> "WorkflowContextBuilder":
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
                    from titan_cli.ai.client import AIClient
                    from titan_cli.ai.exceptions import AIConfigurationError

                    self._ai = AIClient(self._ai_config, self._secrets)
                except AIConfigurationError:
                    self._ai = None
            else:
                self._ai = None
        return self

    def with_git(self, git_client: Optional[Any] = None) -> "WorkflowContextBuilder":
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

    def with_github(self, github_client: Optional[Any] = None) -> "WorkflowContextBuilder":
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


    def build(self) -> WorkflowContext:
        """Build the WorkflowContext."""
        return WorkflowContext(
            secrets=self._secrets,
            ui=self._ui,
            views=self._views,
            ai=self._ai,
            git=self._git,
            github=self._github,
        )
