"""UI model for Git merge results - pre-formatted for display."""
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class MergeStatus(str, Enum):
    """Outcome of a `git merge` invocation."""

    UP_TO_DATE = "up_to_date"
    FAST_FORWARD = "fast_forward"
    MERGED = "merged"
    CONFLICTED = "conflicted"


@dataclass
class UIMergeResult:
    """
    UI model for a merge attempt - formatted for display.

    A CONFLICTED result is not an error: the merge is left in progress with
    MERGE_HEAD set, and `conflicted_files` lists the paths awaiting resolution.
    """

    status: MergeStatus
    source_ref: str  # e.g. "origin/develop"
    target_branch: str  # branch the merge lands on
    conflicted_files: List[str] = field(default_factory=list)
    raw_output: str = ""

    @property
    def has_conflicts(self) -> bool:
        """True when the merge stopped with unresolved conflicts."""
        return self.status == MergeStatus.CONFLICTED

    @property
    def created_commit(self) -> bool:
        """True when the merge produced a merge commit."""
        return self.status == MergeStatus.MERGED
