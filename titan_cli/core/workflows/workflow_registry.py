from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from dataclasses import dataclass
from copy import deepcopy

from titan_cli.core.plugins.plugin_registry import PluginRegistry

from .workflow_sources import (
    WorkflowSource,
    ProjectWorkflowSource,
    UserWorkflowSource,
    SystemWorkflowSource,
    PluginWorkflowSource,
    WorkflowInfo,
)
from .workflow_exceptions import WorkflowNotFoundError, WorkflowError


@dataclass
class ParsedWorkflow:
    """
    A fully parsed, resolved, and merged workflow, ready to be executed.
    This is the output of the registry's 'get_workflow' method.
    """

    name: str
    description: str
    source: str
    steps: List[Dict[str, Any]]
    params: Dict[str, Any]


class WorkflowRegistry:
    """
    Central registry for discovering and managing workflows from all sources.

    This class is analogous to PluginRegistry. It discovers workflows from
    various sources (project, user, system, plugins), resolves 'extends'
    chains, merges configurations, and caches the final, parsed workflows.
    """

    def __init__(self, project_root: Path, plugin_registry: PluginRegistry):
        """
        Initialize the WorkflowRegistry.

        Args:
            project_root: Root path of the current project
            plugin_registry: Registry of installed plugins
        """
        self.project_root = project_root
        self.plugin_registry = plugin_registry

        # Define the base path for system workflows, assuming it's in the root of the package
        # (e.g., titan_cli/workflows). The path is constructed relative to this file's location.
        system_workflows_path = (
            Path(__file__).resolve().parent.parent.parent / "workflows"
        )

        # Workflow sources are listed in order of precedence (highest to lowest).
        self._sources: List[WorkflowSource] = [
            ProjectWorkflowSource(project_root / ".titan" / "workflows"),
            UserWorkflowSource(Path.home() / ".titan" / "workflows"),
            SystemWorkflowSource(system_workflows_path),
            PluginWorkflowSource(plugin_registry),
        ]

        # Cache for fully parsed workflows (similar to PluginRegistry._plugins).
        self._workflows: Dict[str, ParsedWorkflow] = {}

        # Cache for discovered workflow metadata (to avoid re-scanning files).
        self._discovered: Optional[List[WorkflowInfo]] = None

    def discover(self) -> List[WorkflowInfo]:
        """
        Discovers all available workflows from all registered sources.
        
        This method respects precedence; if a workflow with the same name
        exists in multiple sources, only the one from the highest-precedence
        source is included.
        
        Returns:
            A list of WorkflowInfo objects for all unique, discoverable workflows.
        """
        # Return from cache if already discovered
        if self._discovered is not None:
            return self._discovered

        workflows: List[WorkflowInfo] = []
        seen_names = set()

        for source in self._sources:
            try:
                for workflow_info in source.discover():
                    if workflow_info.name not in seen_names:
                        workflows.append(workflow_info)
                        seen_names.add(workflow_info.name)
            except Exception: # Catch all exceptions from source discovery
                pass # Log internally if a logging system is set up, but do not print or fail discovery

        self._discovered = workflows
        return workflows

    def list_available(self) -> List[str]:
        """
        Returns a simple list of the names of all available workflows.
        
        Similar to PluginRegistry.list_installed().
        """
        return [wf.name for wf in self.discover()]

    def get_workflow(self, name: str) -> Optional[ParsedWorkflow]:
        """
        Gets a fully parsed and resolved workflow by its name.

        This is the main entry point for fetching a workflow for execution.
        It handles finding the file, resolving the 'extends' chain,
        merging configurations, and caching the result.

        Similar to PluginRegistry.get_plugin().
        """
        # Return from cache if available
        if name in self._workflows:
            return self._workflows[name]

        # Find the highest-precedence workflow file for the given name
        workflow_file = self._find_workflow_file(name)
        if not workflow_file:
            return None

        # Load, parse, merge, and validate the workflow
        try:
            parsed_workflow = self._load_and_parse(name, workflow_file)
            # Cache the successfully parsed workflow
            self._workflows[name] = parsed_workflow
            return parsed_workflow
        except (WorkflowNotFoundError, yaml.YAMLError) as e:
            # Propagate specific workflow errors for upstream handling (e.g., UI display)
            raise e
        except Exception as e:
            # Catch any other unexpected errors during parsing/merging
            raise WorkflowError(f"An unexpected error occurred while loading workflow '{name}': {e}") from e


    def _find_workflow_file(self, name: str) -> Optional[Path]:
        """Finds a workflow file by name, respecting source precedence."""
        for source in self._sources:
            path = source.find(name)
            if path:
                return path
        return None

    def _load_and_parse(self, name: str, file_path: Path) -> ParsedWorkflow:
        """Loads and parses a single workflow file, resolving its 'extends' chain."""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Resolve 'extends' chain if present
        if "extends" in config:
            base_config = self._resolve_extends(config["extends"])
            config = self._merge_configs(base_config, config)

        # Create the final ParsedWorkflow object
        return ParsedWorkflow(
            name=config.get("name", name),
            description=config.get("description", ""),
            source=self._get_source_name_from_path(file_path),
            steps=config.get("steps", []),
            params=config.get("params", {}),
        )

    def _resolve_extends(self, extends_ref: str) -> Dict[str, Any]:
        """
        Recursively resolves a base workflow from an 'extends' reference.
        
        Supports:
        - "plugin:github/create-pr"
        - "system/quick-commit"
        - "create-pr" (resolved by precedence)
        """
        # Parse the extends reference to find the correct file
        base_workflow_path = None
        if ":" in extends_ref:
            source_type, ref_path = extends_ref.split(":", 1)
            # Find a source that matches the type (e.g., 'plugin')
            for source in self._sources:
                # This logic assumes plugin source names are like "plugin:github", "plugin:git"
                if source.name == source_type or source.name.startswith(f"{source_type}:"):
                    base_workflow_path = source.find(ref_path)
                    if base_workflow_path:
                        break
            if not base_workflow_path:
                 raise WorkflowNotFoundError(f"Base workflow '{extends_ref}' not found in source '{source_type}'.")
        else:
            # Normal resolution across all sources by precedence
            base_workflow_path = self._find_workflow_file(extends_ref)

        if not base_workflow_path:
            raise WorkflowNotFoundError(f"Base workflow '{extends_ref}' not found.")

        # Load the base configuration from the file
        with open(base_workflow_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f) or {}

        # If the base itself extends another workflow, resolve it recursively
        if "extends" in base_config:
            parent_config = self._resolve_extends(base_config["extends"])
            return self._merge_configs(parent_config, base_config)

        return base_config

    def _merge_configs(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merges an overlay configuration into a base configuration.
        - Metadata: overlay wins
        - Params: overlay wins (shallow merge)
        - Steps: merged via hooks
        """
        merged = deepcopy(base)

        # Merge metadata
        for key in ["name", "description", "category"]:
            if key in overlay:
                merged[key] = overlay[key]

        # Merge params (shallow merge, overlay takes precedence)
        if "params" in overlay:
            merged.setdefault("params", {}).update(overlay["params"])

        # Merge steps using hooks defined in the overlay
        if "hooks" in overlay and isinstance(overlay["hooks"], dict):
            merged["steps"] = self._merge_steps_with_hooks(
                base_steps=base.get("steps", []),
                hooks=overlay["hooks"]
            )
        # If overlay specifies its own steps, it is in full control.
        # This is implicitly handled by deepcopy and then not entering the hooks block.
        # If 'steps' key is present in overlay, it completely replaces base 'steps' during deepcopy
        # before the hooks logic is applied, if no 'hooks' are in overlay for step merging.
        # So, if overlay.steps exists AND overlay.hooks is empty/not a dict, overlay.steps takes precedence.
        elif "steps" in overlay:
             merged["steps"] = overlay["steps"]


        return merged
    
    def _merge_steps_with_hooks(self, base_steps: List[Dict], hooks: Dict[str, List[Dict]]) -> List[Dict]:
        """Injects steps from the 'hooks' dictionary into the base step list."""
        merged = []

        for step in base_steps:
            # Check if the current step is a hook point
            if "hook" in step and isinstance(step["hook"], str):
                hook_name = step["hook"]
                # If the overlay provides steps for this hook, inject them
                if hook_name in hooks:
                    # The value from the hooks dict should be a list of step dicts
                    injected_steps = hooks[hook_name]
                    if isinstance(injected_steps, list):
                        merged.extend(injected_steps)
            else:
                # This is a regular step, just append it
                merged.append(step)

        # Handle implicit 'after' hook for steps to be added at the very end
        if "after" in hooks: # User's example used "after" as a hook name, not "after_workflow"
            after_steps = hooks["after"]
            if isinstance(after_steps, list):
                merged.extend(after_steps)

        return merged

    def _get_source_name_from_path(self, file_path: Path) -> str:
        """Determines the source ('project', 'user', etc.) from a file path."""
        for source in self._sources:
            if source.contains(file_path):
                return source.name
        return "unknown"

    def reload(self):
        """Clears all caches, forcing re-discovery and re-parsing."""
        self._workflows.clear()
        self._discovered = None

