"""
OAuth Helper for AI Providers

Handles OAuth authentication for providers that support it (e.g., Gemini with gcloud).
"""

import subprocess
from typing import Optional, Tuple
from dataclasses import dataclass

from titan_cli.clients.gcloud_client import GCloudClient, GCloudClientError


@dataclass
class OAuthStatus:
    """OAuth authentication status"""
    available: bool
    authenticated: bool
    account: Optional[str] = None
    error: Optional[str] = None


class OAuthHelper:
    """
    Helper for OAuth authentication with AI providers

    Currently supports:
    - Google Cloud OAuth (gcloud) for Gemini

    Examples:
        >>> helper = OAuthHelper()
        >>> status = helper.check_gcloud_auth()
        >>> if status.authenticated:
        ...     print(f"Authenticated as: {status.account}")
    """

    def __init__(self, gcloud_client: Optional[GCloudClient] = None):
        self.gcloud = gcloud_client or GCloudClient()

    def check_gcloud_auth(self) -> OAuthStatus:
        """
        Check if Google Cloud CLI is installed and authenticated

        Returns:
            OAuthStatus with authentication information
        """
        if not self.gcloud.is_installed():
            return OAuthStatus(
                available=False,
                authenticated=False,
                error="gcloud CLI not installed"
            )

        try:
            account = self.gcloud.get_active_account()
            if account:
                return OAuthStatus(
                    available=True,
                    authenticated=True,
                    account=account
                )
            else:
                return OAuthStatus(
                    available=True,
                    authenticated=False,
                    error="No active gcloud account found"
                )
        except GCloudClientError as e:
            return OAuthStatus(
                available=True, # It's installed, but auth failed
                authenticated=False,
                error=str(e)
            )

    @staticmethod
    def get_install_instructions() -> str:
        """
        Get installation instructions for gcloud CLI

        Returns:
            Formatted installation instructions
        """
        return """Install Google Cloud CLI:

1. Visit: https://cloud.google.com/sdk/docs/install
2. Download and install for your platform
3. Run: gcloud init
4. Run: gcloud auth application-default login

This will authenticate your Google account for use with Gemini."""

    @staticmethod
    def get_auth_instructions() -> str:
        """
        Get authentication instructions for gcloud

        Returns:
            Formatted authentication instructions
        """
        return """Authenticate with Google Cloud:

Run: gcloud auth application-default login

This will open your browser to sign in with your Google account."""

    def validate_gcloud_auth(self) -> Tuple[bool, Optional[str]]:
        """
        Validate that gcloud auth is properly configured

        Returns:
            Tuple of (is_valid, error_message)
        """
        status = self.check_gcloud_auth()

        if not status.available:
            return False, status.error

        if not status.authenticated:
            return False, "Not authenticated. Run: gcloud auth application-default login"

        return True, None
