# plugins/titan-plugin-github/titan_plugin_github/utils.py
import subprocess
import re
from typing import Tuple, Optional
from .models import PRSizeEstimation

def get_pr_size_estimation(branch_diff: str) -> PRSizeEstimation:
    """
    Analyzes a git diff to estimate PR size and suggest character limits.

    Args:
        branch_diff: The full text of the git diff.

    Returns:
        A PRSizeEstimation object with size category and character limits.
    """
    diff_lines = len(branch_diff.split('\n'))

    # Estimate files changed (count file headers in diff)
    file_pattern = r'^diff --git'
    files_changed = len(re.findall(file_pattern, branch_diff, re.MULTILINE))

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
