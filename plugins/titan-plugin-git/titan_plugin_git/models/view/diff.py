"""UI model for per-file diff churn - pre-formatted for display."""
from dataclasses import dataclass


@dataclass
class UIFileChurn:
    """
    UI model for one file's change counters in a diff.

    Binary files have no line counters (`git diff --numstat` prints "-"),
    so `is_binary` is True and both counters are 0.
    """

    path: str
    additions: int
    deletions: int
    is_binary: bool = False

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions
