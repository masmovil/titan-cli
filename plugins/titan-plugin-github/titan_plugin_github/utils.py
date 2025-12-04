# plugins/titan-plugin-github/titan_plugin_github/utils.py
import subprocess
import re
from typing import Tuple, Optional

def detect_github_repo() -> Tuple[Optional[str], Optional[str]]:
    """
    Auto-detects GitHub repository owner and name from the git remote URL.

    Returns:
        A tuple containing (repo_owner, repo_name) if detected, otherwise (None, None).
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True
        )
        url = result.stdout.strip()

        # Parse: git@github.com:owner/repo.git
        # or https://github.com/owner/repo.git
        match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', url)
        if match:
            return match.group(1), match.group(2)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # git CLI not found or not a git repository
        pass

    return None, None
