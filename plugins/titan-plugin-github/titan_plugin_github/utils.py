# plugins/titan-plugin-github/titan_plugin_github/utils.py
"""Utility functions for GitHub plugin."""

import re
from dataclasses import dataclass


# Default limits for diff processing
DEFAULT_MAX_DIFF_SIZE = 8000  # Characters
DEFAULT_MAX_FILES_IN_DIFF = 50
DEFAULT_MAX_COMMITS_TO_ANALYZE = 15


@dataclass
class PRSizeEstimation:
    """
    PR size estimation with character limits.

    Attributes:
        pr_size: Size category (small, medium, large, very large)
        max_chars: Maximum characters for PR description
        files_changed: Number of files changed
        diff_lines: Number of lines in diff
    """
    pr_size: str
    max_chars: int
    files_changed: int
    diff_lines: int


def calculate_pr_size(diff: str) -> PRSizeEstimation:
    """
    Analyzes a git diff to estimate PR size and suggest character limits.

    This is the single source of truth for PR size calculation.
    Both PRAgent and workflow steps use this function.

    Args:
        diff: The full text of the git diff

    Returns:
        PRSizeEstimation with size category and character limits

    Examples:
        >>> diff = "diff --git a/file.py b/file.py\\n..."
        >>> estimation = calculate_pr_size(diff)
        >>> print(estimation.pr_size)
        'small'
    """
    diff_lines = len(diff.split('\n'))

    # Count files changed (count file headers in diff)
    file_pattern = r'^diff --git'
    files_changed = len(re.findall(file_pattern, diff, re.MULTILINE))

    # Dynamic character limit based on PR size
    if files_changed <= 3 and diff_lines < 100:
        # Small PR: bug fix, doc update, small feature
        max_chars = 500
        pr_size = "small"
    elif files_changed <= 10 and diff_lines < 500:
        # Medium PR: feature, moderate refactor
        max_chars = 1200
        pr_size = "medium"
    elif files_changed <= 30 and diff_lines < 2000:
        # Large PR: architectural changes, new modules
        max_chars = 2000
        pr_size = "large"
    else:
        # Very large PR: major refactor, breaking changes
        max_chars = 3000
        pr_size = "very large"

    return PRSizeEstimation(
        pr_size=pr_size,
        max_chars=max_chars,
        files_changed=files_changed,
        diff_lines=diff_lines
    )


__all__ = ["calculate_pr_size", "PRSizeEstimation"]
