# clients/gcloud_client.py
import subprocess
from typing import Optional

class GCloudClientError(Exception):
    """Custom exception for GCloudClient errors."""
    pass

class GCloudClient:
    """A wrapper for interacting with the gcloud CLI."""

    def is_installed(self) -> bool:
        """Check if the gcloud CLI is installed and available in the system's PATH."""
        try:
            result = subprocess.run(
                ["gcloud", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False  # Don't raise CalledProcessError on non-zero exit
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_active_account(self) -> Optional[str]:
        """
        Retrieves the active, authenticated gcloud account.

        Returns:
            The account email (str) if authenticated, otherwise None.

        Raises:
            GCloudClientError: If the gcloud command fails.
        """
        try:
            result = subprocess.run(
                ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True  # Raise CalledProcessError on non-zero exit
            )
            account = result.stdout.strip()
            return account if account else None
        except FileNotFoundError:
            # This case is handled by is_installed, but included for robustness
            raise GCloudClientError("gcloud CLI not found.")
        except subprocess.CalledProcessError as e:
            raise GCloudClientError(f"gcloud command failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise GCloudClientError("gcloud command timed out.")
