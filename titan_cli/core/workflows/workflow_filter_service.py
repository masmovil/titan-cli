"""
Workflow Filter Service

Service for filtering and grouping workflows by plugin.
"""
from typing import Dict, List, Set

from .workflow_sources import WorkflowInfo


class WorkflowFilterService:
    """Service for filtering and grouping workflows."""

    @staticmethod
    def detect_plugin_name(wf_info: WorkflowInfo) -> str:
        """
        Detect the actual plugin name for a workflow.

        This method intelligently detects which plugin a workflow belongs to,
        even for project/user workflows that use plugin steps.

        Args:
            wf_info: WorkflowInfo object to analyze

        Returns:
            Plugin name in capitalized form (e.g., "Github", "Jira", "Custom")

        Examples:
            Plugin workflow: "plugin:github" -> "Github"
            Project workflow using GitHub steps -> "Github"
            Project workflow using Jira steps -> "Jira"
            Project workflow with no plugins -> "Custom"
            Workflow with explicit `category:` in its YAML -> that category, verbatim
        """
        # An explicit `category:` in the workflow YAML always wins over auto-detection.
        # Lets a workflow that incidentally uses a plugin step (e.g. `github`) stay
        # grouped under its own project/team category instead of that plugin's tab.
        if wf_info.category:
            return wf_info.category

        # If it's already from a plugin, extract the name
        if wf_info.source.startswith("plugin:"):
            plugin_name = wf_info.source.split(":", 1)[1]
            return plugin_name.capitalize()

        # User workflows always go to "Personal" category
        if wf_info.source == "user":
            return "Personal"

        # For project workflows, check which plugin they use
        if wf_info.source == "project":
            if wf_info.required_plugins:
                # Filter out core/project pseudo-plugins
                real_plugins = [p for p in wf_info.required_plugins if p not in ["core", "project"]]
                # If workflow uses multiple plugins, treat as custom/project workflow
                if len(real_plugins) > 1:
                    return "Project"
                elif len(real_plugins) == 1:
                    # Single plugin dependency
                    return real_plugins[0].capitalize()
            # No plugin dependencies, it's a plain project workflow
            return "Project"

        # Fallback for other sources (e.g. user → "Custom")
        return wf_info.source.capitalize()

    @staticmethod
    def group_by_plugin(workflows: List[WorkflowInfo]) -> Dict[str, List[WorkflowInfo]]:
        """
        Group workflows by their associated plugin.

        Analyzes each workflow to determine its plugin and creates a mapping
        from plugin names to lists of workflows.

        Args:
            workflows: List of WorkflowInfo objects to group

        Returns:
            Dictionary mapping plugin names to lists of workflows

        Example:
            {
                "Github": [workflow1, workflow2],
                "Jira": [workflow3],
                "Custom": [workflow4]
            }
        """
        plugin_map: Dict[str, List[WorkflowInfo]] = {}

        for wf_info in workflows:
            plugin_name = WorkflowFilterService.detect_plugin_name(wf_info)

            if plugin_name not in plugin_map:
                plugin_map[plugin_name] = []
            plugin_map[plugin_name].append(wf_info)

        return plugin_map

    @staticmethod
    def get_unique_plugin_names(workflows: List[WorkflowInfo]) -> Set[str]:
        """
        Get all unique plugin names from a list of workflows.

        Args:
            workflows: List of WorkflowInfo objects

        Returns:
            Set of unique plugin names
        """
        plugin_names = set()
        for wf_info in workflows:
            plugin_name = WorkflowFilterService.detect_plugin_name(wf_info)
            plugin_names.add(plugin_name)
        return plugin_names

    @staticmethod
    def filter_by_plugin(workflows: List[WorkflowInfo], plugin_name: str) -> List[WorkflowInfo]:
        """
        Filter workflows by plugin name.

        Args:
            workflows: List of WorkflowInfo objects to filter
            plugin_name: Plugin name to filter by (e.g., "Github")

        Returns:
            List of workflows that belong to the specified plugin
        """
        return [
            wf for wf in workflows
            if WorkflowFilterService.detect_plugin_name(wf) == plugin_name
        ]

    @staticmethod
    def remove_duplicates(workflows: List[WorkflowInfo]) -> List[WorkflowInfo]:
        """
        Remove duplicate workflows by name, keeping first occurrence.

        Args:
            workflows: List of WorkflowInfo objects that may contain duplicates

        Returns:
            List of unique workflows (by name)
        """
        seen = set()
        unique_workflows = []

        for wf in workflows:
            if wf.name not in seen:
                seen.add(wf.name)
                unique_workflows.append(wf)

        return unique_workflows

    @staticmethod
    def sort_favorites_first(workflows: List[WorkflowInfo], favorite_names: Set[str]) -> List[WorkflowInfo]:
        """
        Sort workflows so favorited ones appear first.

        Uses a stable sort, so relative order is preserved within both the
        favorited group and the non-favorited group.

        Args:
            workflows: List of WorkflowInfo objects to sort
            favorite_names: Set of favorited workflow names (WorkflowInfo.name)

        Returns:
            New list with favorites first, in original relative order, followed
            by non-favorites, also in original relative order.
        """
        return sorted(workflows, key=lambda wf: wf.name not in favorite_names)
