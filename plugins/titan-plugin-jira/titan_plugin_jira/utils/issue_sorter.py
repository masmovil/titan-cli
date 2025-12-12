"""
Issue Sorter Utility

Provides intelligent sorting for JIRA issues based on status, priority, and key.
"""

from typing import List, Dict
from dataclasses import dataclass


@dataclass
class IssueSortConfig:
    """Configuration for issue sorting priorities."""

    status_order: Dict[str, int]
    priority_order: Dict[str, int]

    @classmethod
    def default(cls) -> "IssueSortConfig":
        """
        Returns default sorting configuration.

        Status order: To Do → In Progress → Done
        Priority order: Critical → High → Medium → Low
        """
        return cls(
            status_order={
                # To Do / Open states
                "to do": 0,
                "open": 0,
                "backlog": 0,
                # In Progress states
                "in progress": 1,
                "in review": 1,
                "code review": 1,
                "review": 1,
                # Done / Closed states
                "done": 2,
                "closed": 2,
                "resolved": 2,
                "completed": 2
            },
            priority_order={
                # Critical/Highest
                "critical": 0,
                "highest": 0,
                "blocker": 0,
                # High
                "high": 1,
                # Medium/Normal
                "medium": 2,
                "normal": 2,
                # Low/Lowest
                "low": 3,
                "lowest": 3,
                "trivial": 3
            }
        )


class IssueSorter:
    """
    Sorts JIRA issues intelligently based on status, priority, and key.

    Sorting criteria (in order):
    1. Status (To Do → In Progress → Done)
    2. Priority (Critical → High → Medium → Low)
    3. Key (alphabetical)

    Unknown statuses/priorities are placed at the end.

    Example:
        >>> from titan_plugin_jira.models import JiraTicket
        >>> sorter = IssueSorter()
        >>> sorted_issues = sorter.sort(issues)
    """

    def __init__(self, config: IssueSortConfig = None):
        """
        Initialize the sorter with optional custom configuration.

        Args:
            config: IssueSortConfig instance. If None, uses default configuration.
        """
        self.config = config or IssueSortConfig.default()
        self._unknown_value = 99  # Value for unknown statuses/priorities

    def sort(self, issues: List) -> List:
        """
        Sort issues based on status, priority, and key.

        Args:
            issues: List of JiraTicket objects

        Returns:
            Sorted list of JiraTicket objects

        Example:
            >>> sorter = IssueSorter()
            >>> sorted_issues = sorter.sort(my_issues)
        """
        return sorted(issues, key=self._sort_key)

    def _sort_key(self, issue) -> tuple:
        """
        Generate sort key for an issue.

        Returns tuple of (status_order, priority_order, key) for sorting.
        """
        status_value = self._get_status_order(issue.status)
        priority_value = self._get_priority_order(issue.priority)

        return (status_value, priority_value, issue.key)

    def _get_status_order(self, status: str) -> int:
        """Get sort order for a status (case-insensitive)."""
        if not status:
            return self._unknown_value
        return self.config.status_order.get(
            status.lower(),
            self._unknown_value
        )

    def _get_priority_order(self, priority: str) -> int:
        """Get sort order for a priority (case-insensitive)."""
        if not priority:
            return self._unknown_value
        return self.config.priority_order.get(
            priority.lower(),
            self._unknown_value
        )

    def get_sort_description(self) -> str:
        """
        Get human-readable description of the sort order.

        Returns:
            Description string like "Status → Priority → Key"
        """
        return "Status → Priority → Key"
