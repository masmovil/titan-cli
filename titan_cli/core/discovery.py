"""
Project Discovery Module

Scans a root directory to find and categorize projects based on whether
they are configured with Titan.
"""

from pathlib import Path
from typing import List, Tuple

def discover_projects(root_path_str: str) -> Tuple[List[Path], List[Path]]:
    """
    Scans a root directory and discovers configured and unconfigured projects.

    An "unconfigured" project is identified as a directory containing a .git folder.
    A "configured" project is one that also contains a .titan/config.toml file.

    Args:
        root_path_str: The absolute path to the root directory to scan.

    Returns:
        A tuple containing two lists:
        - A list of paths to configured projects.
        - A list of paths to unconfigured projects.
    """
    configured_projects: List[Path] = []
    unconfigured_projects: List[Path] = []

    root_path = Path(root_path_str).expanduser().resolve()
    if not root_path.is_dir():
        return [], []

    # Iterate through items in the root directory
    for item in root_path.iterdir():
        try:
            # We only care about directories
            if item.is_dir():
                is_git_repo = (item / ".git").is_dir()
                is_titan_project = (item / ".titan" / "config.toml").is_file()

                if is_titan_project:
                    # If it has a titan config, it's definitely a configured project
                    configured_projects.append(item)
                elif is_git_repo:
                    # If it's a git repo but not a titan project, it's unconfigured
                    unconfigured_projects.append(item)
        except PermissionError:
            # Skip directories we don't have permission to access
            continue

    return sorted(configured_projects), sorted(unconfigured_projects)
