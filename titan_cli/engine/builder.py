"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""
from typing import Optional, Any

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from .context import WorkflowContext
from .ui_container import UIComponents
from .views_container import UIViews


class WorkflowContextBuilder:
    """
    Fluent builder for WorkflowContext.
    
    Example:
        config = TitanConfig()
        secrets = SecretManager()
        ctx = WorkflowContextBuilder(config, secrets) \\
            .with_ui() \\
            .with_ai() \\
            .build()
    """

    def __init__(self, config: TitanConfig, secrets: SecretManager):
        """
        Initialize builder.
        
        Args:
            config: The TitanConfig instance.
            secrets: The SecretManager instance.
        """
        self._config = config
        self._secrets = secrets

        # UI containers
        self._ui: Optional[UIComponents] = None
        self._views: Optional[UIViews] = None

        # Service clients
        self._ai = None
        self._git = None

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
            # Convenience - auto-create from config
            try:
                from titan_cli.ai.client import AIClient
                from titan_cli.ai.exceptions import AIConfigurationError

                self._ai = AIClient(self._config, self._secrets)
            except AIConfigurationError:
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
            git_plugin = self._config.registry.get_plugin("git")
            if git_plugin and git_plugin.is_available():
                try:
                    self._git = git_plugin.get_client()
                except Exception: # Catch any exception during client retrieval
                    self._git = None # Fail silently
            else:
                self._git = None
        return self

    def build(self) -> WorkflowContext:
        """Build the WorkflowContext."""
        return WorkflowContext(
            config=self._config,
            secrets=self._secrets,
            ui=self._ui,
            views=self._views,
            ai=self._ai,
            git=self._git,
        )
