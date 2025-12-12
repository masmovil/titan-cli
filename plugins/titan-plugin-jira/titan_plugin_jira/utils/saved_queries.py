"""
Predefined JIRA saved queries registry.

Common JQL queries that can be used across projects.
Projects can extend these with custom queries in .titan/config.toml
"""

from typing import Dict


class SavedQueries:
    """
    Registry of predefined JQL queries.

    These are common queries that work with any JIRA instance.
    Projects can override or extend these via config.
    """

    # ==================== PERSONAL QUERIES ====================

    OPEN_ISSUES = 'project = {project} AND status IN ("Open", "Ready to Dev") ORDER BY updated DESC'
    """All issues that are Open or Ready to Dev in the specified project (regardless of assignee), ordered by last updated"""

    MY_OPEN_ISSUES = 'project = {project} AND assignee = currentUser() AND status IN ("Open", "Ready to Dev") ORDER BY updated DESC'
    """Issues assigned to you that are Open or Ready to Dev in the specified project"""

    MY_ISSUES = "assignee = currentUser() ORDER BY updated DESC"
    """All issues assigned to you (including Done)"""

    MY_BUGS = "assignee = currentUser() AND type = Bug AND status != Done"
    """Open bugs assigned to you"""

    MY_IN_REVIEW = "assignee = currentUser() AND status = 'In Review'"
    """Issues you have in review status"""

    MY_IN_PROGRESS = "assignee = currentUser() AND status = 'In Progress'"
    """Issues you're currently working on"""

    REPORTED_BY_ME = "reporter = currentUser() ORDER BY created DESC"
    """Issues you created"""

    # ==================== TEAM QUERIES ====================

    CURRENT_SPRINT = "sprint in openSprints() AND project = {project}"
    """Issues in current sprint (requires project parameter)"""

    TEAM_OPEN = "project = {project} AND status != Done"
    """All open issues in project"""

    TEAM_BUGS = "project = {project} AND type = Bug AND status != Done"
    """Open bugs in project"""

    TEAM_IN_REVIEW = "project = {project} AND status = 'In Review'"
    """Issues in review for project"""

    TEAM_READY_FOR_QA = "project = {project} AND status = 'Ready for QA'"
    """Issues ready for QA testing"""

    # ==================== PRIORITY QUERIES ====================

    CRITICAL_ISSUES = "priority = Highest AND status != Done ORDER BY created ASC"
    """All critical priority issues"""

    HIGH_PRIORITY = "priority IN (Highest, High) AND status != Done ORDER BY priority DESC"
    """High and highest priority issues"""

    CRITICAL_MY_PROJECT = "priority = Highest AND status != Done AND project = {project}"
    """Critical issues in specific project"""

    BLOCKED_ISSUES = "status = Blocked ORDER BY updated DESC"
    """All blocked issues"""

    # ==================== TIME-BASED QUERIES ====================

    UPDATED_TODAY = "updated >= startOfDay() ORDER BY updated DESC"
    """Issues updated today"""

    UPDATED_THIS_WEEK = "updated >= startOfWeek() ORDER BY updated DESC"
    """Issues updated this week"""

    CREATED_TODAY = "created >= startOfDay() ORDER BY created DESC"
    """Issues created today"""

    CREATED_THIS_WEEK = "created >= startOfWeek() ORDER BY created DESC"
    """Issues created this week"""

    RECENT_BUGS = "type = Bug AND created >= -7d ORDER BY created DESC"
    """Bugs created in last 7 days"""

    # ==================== STATUS QUERIES ====================

    TODO_ISSUES = "status = 'To Do' ORDER BY priority DESC, created ASC"
    """All issues in To Do status"""

    IN_PROGRESS_ALL = "status = 'In Progress' ORDER BY updated DESC"
    """All issues currently in progress"""

    IN_REVIEW_ALL = "status = 'In Review' ORDER BY updated DESC"
    """All issues in review"""

    DONE_RECENTLY = "status = Done AND updated >= -7d ORDER BY updated DESC"
    """Issues completed in last 7 days"""

    @classmethod
    def get_all(cls) -> Dict[str, str]:
        """
        Get all predefined queries as a dictionary.

        Returns:
            Dict mapping query names to JQL strings
        """
        queries = {}
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith('_'):
                value = getattr(cls, attr)
                if isinstance(value, str):
                    # Convert attribute name to lowercase with underscores
                    key = attr.lower()
                    queries[key] = value
        return queries

    @classmethod
    def format(cls, query_name: str, **params) -> str:
        """
        Format a query with parameters.

        Args:
            query_name: Name of the query (lowercase with underscores)
            **params: Parameters to format into query

        Returns:
            Formatted JQL query

        Example:
            >>> SavedQueries.format('current_sprint', project='ECAPP')
            'sprint in openSprints() AND project = ECAPP'
        """
        queries = cls.get_all()
        if query_name not in queries:
            raise ValueError(f"Query '{query_name}' not found")

        query = queries[query_name]
        return query.format(**params)


# Singleton instance
SAVED_QUERIES = SavedQueries()


__all__ = ["SavedQueries", "SAVED_QUERIES"]
