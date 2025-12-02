"""
WorkflowContext - Dependency injection container for workflows.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from .ui_container import UIComponents
from .views_container import UIViews

if TYPE_CHECKING:
    from titan_cli.ai.client import AIClient


@dataclass
class WorkflowContext:
    """
    Context container for workflow execution.
    
    Provides:
    - Dependency injection (clients, services)
    - Shared data storage between steps
    - UI components (organized by level)
    - Access to configuration and secrets
    
    UI Architecture:
        ctx.ui.text      # Basic components (Rich wrappers)
        ctx.ui.panel
        ctx.ui.table
        ctx.ui.spacer
        
        ctx.views.prompts  # Composed views
        ctx.views.menu
    """

    # Core dependencies
    config: TitanConfig
    secrets: SecretManager

    # UI (two-level architecture)
    ui: Optional[UIComponents] = None
    views: Optional[UIViews] = None

    # Service clients (populated by builder)
    ai: Optional["AIClient"] = None

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set shared data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get shared data."""
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if key exists in shared data."""
        return key in self.data
