# plugins/titan-plugin-jira/titan_plugin_jira/exceptions.py
"""Custom exceptions for JIRA plugin."""

from typing import Dict, Optional


class JiraPluginError(Exception):
    """Base exception for JIRA plugin errors."""
    pass


class JiraConfigurationError(JiraPluginError):
    """Raised when JIRA plugin configuration is invalid or missing."""
    pass


class JiraClientError(JiraPluginError):
    """Raised when JIRA client operations fail."""
    pass


class JiraAPIError(Exception):
    """Exception raised for JIRA API errors"""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


__all__ = [
    "JiraPluginError",
    "JiraConfigurationError",
    "JiraClientError",
    "JiraAPIError",
]
