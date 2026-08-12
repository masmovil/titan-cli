"""Prompt-budget policy for GitHub AI review workflows.

Centralizes the content-budget sizing and batch fit/split/degradation
policy previously duplicated as free functions in
`context_resolution_operations.py` and `code_review_steps.py`.
"""

from ..models.review_enums import FileReadMode, PRSizeClass
from ..models.review_models import FileContextEntry, FocusContextBatch, ReviewStrategy


class PromptBudgetManager:
    """Owns prompt-part sizing, batch fit/split decisions, and degradation policy."""

    # A worktree_reference entry is just a short hint in the prompt text, but the CLI still
    # has to open and analyze the real file from the worktree with its own tools, so its
    # actual cost is much higher than its prompt-text size suggests.
    WORKTREE_REFERENCE_ESTIMATED_CHARS = 5000

    def content_budget(self, strategy: ReviewStrategy) -> int:
        """Return the char budget available for file/related/comment context."""
        reserve = 5000 if strategy.size_class in {PRSizeClass.LARGE, PRSizeClass.HUGE} else 3500
        return max(2500, strategy.max_prompt_chars - reserve)

    def estimate_entry_chars(self, entry: FileContextEntry) -> int:
        """Estimate the prompt-budget cost of a resolved file context entry."""
        if entry.full_content:
            return len(entry.full_content)
        if entry.expanded_hunks:
            return sum(len(hunk) for hunk in entry.expanded_hunks)
        if entry.hunks:
            return sum(len(hunk) for hunk in entry.hunks)
        if entry.worktree_reference:
            return self.WORKTREE_REFERENCE_ESTIMATED_CHARS
        return 0

    def fit_batch_to_budget(
        self,
        batch: FocusContextBatch,
        prompt_parts: dict[str, str],
        budget_chars: int,
        allow_file_reads: bool = True,
    ) -> tuple[list[FocusContextBatch], bool]:
        """Shrink or split a batch until it fits the prompt budget, or mark it oversized.

        ``allow_file_reads=False`` forbids the worktree_reference degradation: that
        mode instructs the model to read the file from disk, which is exactly what
        the caller ruled out when the checkout is not provably the PR's revision.
        The batch then degrades through the remaining steps or reports oversized.
        """
        prompt = prompt_parts["prompt"]
        actual_chars = len(prompt)
        if actual_chars <= budget_chars:
            fitted = batch.model_copy(update={"prompt_actual_chars": actual_chars})
            return [fitted], False

        file_items = list(batch.files_context.items())
        if len(file_items) > 1:
            midpoint = max(1, len(file_items) // 2)
            left = batch.model_copy(
                update={
                    "batch_id": f"{batch.batch_id}a",
                    "files_context": dict(file_items[:midpoint]),
                    "degraded_context": True,
                }
            )
            right = batch.model_copy(
                update={
                    "batch_id": f"{batch.batch_id}b",
                    "files_context": dict(file_items[midpoint:]),
                    "degraded_context": True,
                }
            )
            return [left, right], True

        only_path, only_entry = file_items[0]
        if not only_entry.worktree_reference and allow_file_reads:
            degraded_entry = only_entry.model_copy(
                update={
                    "full_content": None,
                    "expanded_hunks": [],
                    "hunks": [],
                    "read_mode": FileReadMode.WORKTREE_REFERENCE,
                    "worktree_reference": True,
                    "review_hint": only_entry.review_hint
                    or "Read this file from the worktree and inspect the changed regions first.",
                    "approximate_chars": min(800, only_entry.approximate_chars or 800),
                }
            )
            return [
                batch.model_copy(
                    update={
                        "files_context": {only_path: degraded_entry},
                        "degraded_context": True,
                    }
                )
            ], True

        if batch.related_files:
            return [batch.model_copy(update={"related_files": {}, "degraded_context": True})], True

        if batch.comment_context:
            return [batch.model_copy(update={"comment_context": [], "degraded_context": True})], True

        oversized = batch.model_copy(
            update={
                "prompt_actual_chars": actual_chars,
                "prompt_still_too_large": True,
                "degraded_context": True,
            }
        )
        return [oversized], False


_default_manager = PromptBudgetManager()


def get_prompt_budget_manager() -> PromptBudgetManager:
    """Return the shared `PromptBudgetManager` instance."""
    return _default_manager
