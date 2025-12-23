from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Set, Protocol
import yaml
from dataclasses import dataclass, field


class PluginRegistryProtocol(Protocol):
    """Protocol defining the interface that PluginRegistry must implement for workflow sources."""

    def list_installed(self) -> List[str]:
        """List successfully loaded plugins."""
        ...

    def get_plugin(self, name: str):
        """Get plugin instance by name."""
        ...

@dataclass
class WorkflowInfo:
    """Metadata about a discovered, but not yet parsed, workflow."""
    name: str
    description: str
    source: str  # "project", "user", "system", "plugin:github"
    path: Path
    category: Optional[str] = None
    required_plugins: Set[str] = field(default_factory=set)

def _parse_workflow_info(file: Path, source_name: str, plugin_registry: PluginRegistryProtocol) -> WorkflowInfo:
    """
    Helper to extract metadata and plugin dependencies from a workflow file.
    Does not resolve 'extends' or nested 'workflow' calls to keep discovery fast.
    """
    try:
        with open(file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        config = {}

    required_plugins: Set[str] = set()
    
    # Check direct plugin dependencies in steps
    steps = config.get("steps", [])
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and "plugin" in step and step["plugin"] not in ["core", "project"]:
                required_plugins.add(step["plugin"])

    # Check 'extends' field for plugin dependencies
    extends_ref = config.get("extends")
    if extends_ref and isinstance(extends_ref, str):
        if extends_ref.startswith("plugin:"):
            # Extract plugin name from "plugin:git/commit-ai" -> "git"
            plugin_part = extends_ref.split(':', 1)[1]
            plugin_name = plugin_part.split('/', 1)[0]
            required_plugins.add(plugin_name)

    return WorkflowInfo(
        name=file.stem,
        description=config.get("description", "No description available."),
        source=source_name,
        path=file,
        category=config.get("category"),
        required_plugins=required_plugins
    )


class WorkflowSource(ABC):
    """
    Abstract base class for a source of workflows.
    This pattern allows discovering workflows from the project, user's home,
    system-wide, or from plugins, in a uniform way.
    """
    def __init__(self, plugin_registry: PluginRegistryProtocol):
        self._plugin_registry = plugin_registry

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the source (e.g., 'project', 'user', 'plugin:github')."""
        pass

    @abstractmethod
    def discover(self) -> List[WorkflowInfo]:
        """Discover all available workflows from this source."""
        pass

    @abstractmethod
    def find(self, name: str) -> Optional[Path]:
        """Find a specific workflow file by its name within this source."""
        pass

    @abstractmethod
    def contains(self, path: Path) -> bool:
        """Check if a given file path belongs to this source."""
        pass

class ProjectWorkflowSource(WorkflowSource):
    """
    Represents workflows defined within the current project
    at the conventional '.titan/workflows/' directory.
    """

    def __init__(self, path: Path, plugin_registry: PluginRegistryProtocol):
        super().__init__(plugin_registry)
        self._path = path.resolve()

    @property
    def name(self) -> str:
        return "project"

    def discover(self) -> List[WorkflowInfo]:
        """Discovers all .yaml or .yml files in the project's workflow directory."""
        if not self._path.is_dir():
            return []

        workflows = []
        for file in self._path.glob("*.yaml"):
            workflows.append(self._to_workflow_info(file))
        for file in self._path.glob("*.yml"):
            if file.stem not in [w.name for w in workflows]: # Avoid duplicates if both .yaml and .yml exist
                workflows.append(self._to_workflow_info(file))
        return workflows

    def find(self, name: str) -> Optional[Path]:
        """Finds a workflow by name in the project directory."""
        yaml_file = self._path / f"{name}.yaml"
        if yaml_file.is_file():
            return yaml_file
        
        yml_file = self._path / f"{name}.yml"
        if yml_file.is_file():
            return yml_file
            
        return None

    def contains(self, path: Path) -> bool:
        """Checks if the given path is within this project's workflow directory."""
        try:
            path.resolve().relative_to(self._path)
            return True
        except ValueError:
            return False

    def _to_workflow_info(self, file: Path) -> WorkflowInfo:
        """Helper to extract metadata from a workflow file."""
        return _parse_workflow_info(file, self.name, self._plugin_registry)

class UserWorkflowSource(WorkflowSource):
    """
    Represents workflows defined by the user in their home directory
    at '~/.titan/workflows/'.
    """

    def __init__(self, path: Path, plugin_registry: PluginRegistryProtocol):
        super().__init__(plugin_registry)
        self._path = path.expanduser().resolve()

    @property
    def name(self) -> str:
        return "user"

    def discover(self) -> List[WorkflowInfo]:
        if not self._path.is_dir():
            return []
        
        workflows = []
        for file in self._path.glob("*.yaml"):
            workflows.append(self._to_workflow_info(file))
        for file in self._path.glob("*.yml"):
            if file.stem not in [w.name for w in workflows]:
                workflows.append(self._to_workflow_info(file))
        return workflows

    def find(self, name: str) -> Optional[Path]:
        yaml_file = self._path / f"{name}.yaml"
        if yaml_file.is_file():
            return yaml_file
        yml_file = self._path / f"{name}.yml"
        if yml_file.is_file():
            return yml_file
        return None

    def contains(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._path)
            return True
        except ValueError:
            return False

    def _to_workflow_info(self, file: Path) -> WorkflowInfo:
        return _parse_workflow_info(file, self.name, self._plugin_registry)

class SystemWorkflowSource(WorkflowSource):
    """
    Represents workflows bundled with the Titan CLI itself,
    typically found in a 'workflows' directory within the installed package.
    """

    def __init__(self, path: Path, plugin_registry: PluginRegistryProtocol):
        super().__init__(plugin_registry)
        self._path = path.resolve()

    @property
    def name(self) -> str:
        return "system"

    def discover(self) -> List[WorkflowInfo]:
        if not self._path.is_dir():
            return []
        
        workflows = []
        for file in self._path.glob("*.yaml"):
            workflows.append(self._to_workflow_info(file))
        for file in self._path.glob("*.yml"):
            if file.stem not in [w.name for w in workflows]:
                workflows.append(self._to_workflow_info(file))
        return workflows

    def find(self, name: str) -> Optional[Path]:
        yaml_file = self._path / f"{name}.yaml"
        if yaml_file.is_file():
            return yaml_file
        yml_file = self._path / f"{name}.yml"
        if yml_file.is_file():
            return yml_file
        return None

    def contains(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._path)
            return True
        except ValueError:
            return False

    def _to_workflow_info(self, file: Path) -> WorkflowInfo:
        return _parse_workflow_info(file, self.name, self._plugin_registry)

class PluginWorkflowSource(WorkflowSource):
    """
    Represents workflows provided by installed Titan plugins.
    Discovers workflows via the `workflows_path` property of `TitanPlugin` instances.
    """

    def __init__(self, plugin_registry: PluginRegistryProtocol): # Remove registry here
        super().__init__(plugin_registry)
        self._plugin_registry = plugin_registry

    @property
    def name(self) -> str:
        return "plugin"

    def discover(self) -> List[WorkflowInfo]:
        workflows = []
        for plugin_name in self._plugin_registry.list_installed():
            plugin_instance = self._plugin_registry.get_plugin(plugin_name)
            if plugin_instance and plugin_instance.workflows_path:
                plugin_workflows_dir = plugin_instance.workflows_path
                if plugin_workflows_dir.is_dir():
                    for file in plugin_workflows_dir.glob("*.yaml"):
                        workflows.append(self._to_workflow_info(file, plugin_name))
                    for file in plugin_workflows_dir.glob("*.yml"):
                        if file.stem not in [w.name for w in workflows]:
                            workflows.append(self._to_workflow_info(file, plugin_name))
        return workflows

    def find(self, name: str) -> Optional[Path]:
        # Handle qualified names like "github/create-pr"
        if "/" in name:
            plugin_name_ref, workflow_name = name.split('/', 1)
            plugin_instance = self._plugin_registry.get_plugin(plugin_name_ref)
            if plugin_instance and plugin_instance.workflows_path:
                plugin_workflows_dir = plugin_instance.workflows_path
                yaml_file = plugin_workflows_dir / f"{workflow_name}.yaml"
                if yaml_file.is_file():
                    return yaml_file
                yml_file = plugin_workflows_dir / f"{workflow_name}.yml"
                if yml_file.is_file():
                    return yml_file
            return None # If qualified name is used, only search that plugin

        # Fallback to original behavior for unqualified names
        for plugin_name in self._plugin_registry.list_installed():
            plugin_instance = self._plugin_registry.get_plugin(plugin_name)
            if plugin_instance and plugin_instance.workflows_path:
                plugin_workflows_dir = plugin_instance.workflows_path
                yaml_file = plugin_workflows_dir / f"{name}.yaml"
                if yaml_file.is_file():
                    return yaml_file
                yml_file = plugin_workflows_dir / f"{name}.yml"
                if yml_file.is_file():
                    return yml_file
        return None

    def contains(self, path: Path) -> bool:
        # This is complex to determine definitively without iterating all plugins.
        # For simplicity, we can assume if a path contains 'plugins' in its parts, it might be a plugin workflow.
        # A more robust check would involve checking against all known plugin_instance.workflows_path.
        return "plugins" in path.parts # Heuristic, might need refinement

    def _to_workflow_info(self, file: Path, plugin_name: str) -> WorkflowInfo:
        info = _parse_workflow_info(file, f"plugin:{plugin_name}", self._plugin_registry) # Pass plugin_registry
        # For plugin workflows, the name is qualified, e.g., "github/create-pr"
        # but the file.stem is just "create-pr". We'll handle this in the registry.
        return info
