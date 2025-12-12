# plugins/titan-plugin-jira/titan_plugin_jira/exceptions.py
"""Custom exceptions for JIRA plugin."""


class JiraPluginError(Exception):
    """Base exception for JIRA plugin errors."""
    pass


class JiraConfigurationError(JiraPluginError):
    """Raised when JIRA plugin configuration is invalid or missing."""
    pass


class JiraClientError(JiraPluginError):
    """Raised when JIRA client operations fail."""
    pass
