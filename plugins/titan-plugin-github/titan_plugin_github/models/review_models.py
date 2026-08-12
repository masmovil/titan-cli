"""
Pydantic models for the code review system.

The new-findings flow is intentionally split into two concerns:
- cheap deterministic selection (manifest, scoring, comments context)
- focused AI review over one or more bounded context batches
"""

from typing import Optional

from pydantic import BaseModel, Field

from .review_enums import (
    ChecklistCategory,
    CommentContextKind,
    ContextRequestType,
    ExclusionReason,
    FileChangeStatus,
    FileReadMode,
    FileReviewPriority,
    FindingSeverity,
    PRSizeClass,
    ReviewActionSource,
    ReviewActionType,
    ReviewStrategyType,
    ThreadDecisionType,
    ThreadSeverity,
)


class ChangedFileEntry(BaseModel):
    """Single file changed in the PR with cheap deterministic signals."""

    path: str = Field(..., description="File path in repo")
    status: FileChangeStatus = Field(..., description="Normalized change type")
    additions: int = Field(default=0, description="Lines added")
    deletions: int = Field(default=0, description="Lines deleted")
    is_test: bool = Field(default=False, description="Whether file is a test")
    size_lines: int = Field(default=0, description="Current file size in lines if known")
    is_docs: bool = Field(default=False, description="Documentation-like file")
    is_generated: bool = Field(default=False, description="Generated or vendored file")
    is_config: bool = Field(default=False, description="Configuration file")
    is_lockfile: bool = Field(default=False, description="Dependency lockfile")
    is_rename_only: bool = Field(default=False, description="Renamed without meaningful edits")

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions


class PullRequestManifest(BaseModel):
    """Basic PR metadata."""

    number: int = Field(..., description="PR number")
    title: str = Field(..., description="PR title")
    base: str = Field(..., description="Base branch")
    head: str = Field(..., description="Head branch")
    author: str = Field(..., description="PR author login")
    description: str = Field(..., description="PR description/body")


class ChangeManifest(BaseModel):
    """Cheap deterministic context extracted from the PR."""

    pr: PullRequestManifest = Field(..., description="PR metadata")
    files: list[ChangedFileEntry] = Field(..., description="Changed files with cheap signals")
    total_additions: int = Field(..., description="Total lines added across all files")
    total_deletions: int = Field(..., description="Total lines deleted across all files")

    def summary(self) -> str:
        return (
            f"PR #{self.pr.number}: {len(self.files)} files changed "
            f"(+{self.total_additions}/-{self.total_deletions})"
        )


class ReviewChecklistItem(BaseModel):
    """Single review category offered to AI."""

    id: ChecklistCategory = Field(..., description="Unique checklist category ID")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this checklist item covers")
    relevant_file_patterns: list[str] = Field(default_factory=list)


class ExistingCommentIndexEntry(BaseModel):
    """Compact dedupe-oriented view of an existing PR comment."""

    comment_id: int = Field(..., description="GitHub comment ID")
    thread_id: str = Field(..., description="Thread ID or general_N")
    is_resolved: bool = Field(..., description="Whether thread is resolved")
    path: Optional[str] = Field(default=None, description="File path")
    line: Optional[int] = Field(default=None, description="Target line")
    category: Optional[str] = Field(default=None, description="Inferred category")
    title: str = Field(..., description="Short comment title/body preview")
    author: str = Field(..., description="Comment author login")
    has_author_reply: bool = False
    last_reply_author: Optional[str] = None
    reply_count: int = 0
    is_adjudicated: bool = False


class CommentThreadSummary(BaseModel):
    """Compressed representation of a review thread for prompt context."""

    thread_id: str
    path: Optional[str] = None
    line: Optional[int] = None
    is_resolved: bool = False
    has_author_reply: bool = False
    last_reply_author: Optional[str] = None
    is_adjudicated: bool = False
    main_issue: str = Field(default="", description="Initial issue raised in the thread")
    latest_state: str = Field(default="", description="Latest visible response or status")
    reply_count: int = 0


class CommentContextEntry(BaseModel):
    """Prompt-ready comment context, either raw compact comment or summarized thread."""

    kind: CommentContextKind = Field(..., description="Representation type")
    thread_id: str
    path: Optional[str] = None
    line: Optional[int] = None
    category: Optional[str] = None
    title: str = Field(default="")
    summary: str = Field(default="")
    is_resolved: bool = False
    has_author_reply: bool = False
    last_reply_author: Optional[str] = None
    reply_count: int = 0
    is_adjudicated: bool = False


class ContextRequest(BaseModel):
    """Request for additional supporting context beyond the diff."""

    type: ContextRequestType
    for_path: str
    reason: str = ""


class FileReviewPlan(BaseModel):
    """Focused plan for one file selected for deeper review."""

    path: str
    priority: FileReviewPriority
    read_mode: FileReadMode
    reasons: list[str] = Field(default_factory=list)


class ExcludedFileEntry(BaseModel):
    """File excluded or trimmed from review focus."""

    path: str
    reason: ExclusionReason
    detail: str = ""


class ReviewPlan(BaseModel):
    """Structured output from planning: what to review, not every changed file."""

    focus_files: list[FileReviewPlan] = Field(default_factory=list)
    review_axes: list[ChecklistCategory] = Field(default_factory=list)
    extra_context_requests: list[ContextRequest] = Field(default_factory=list)
    excluded_files: list[ExcludedFileEntry] = Field(default_factory=list)


class PRClassification(BaseModel):
    """Deterministic classification of PR size and composition."""

    size_class: PRSizeClass
    files_changed: int
    total_lines_changed: int
    doc_files: int = 0
    test_files: int = 0
    config_files: int = 0
    generated_files: int = 0
    comment_threads: int = 0
    comment_entries: int = 0
    high_signal_files: int = 0
    repeated_callsite_files: int = 0
    role_count: int = 0
    roles: list[str] = Field(default_factory=list)
    complexity_score: int = 0
    active_review: bool = False
    is_repetitive_migration: bool = False
    rationale: str = ""


class ScoredReviewCandidate(BaseModel):
    """File candidate ranked before AI planning."""

    path: str
    score: int
    priority: FileReviewPriority
    suggested_read_mode: FileReadMode
    reasons: list[str] = Field(default_factory=list)


class ReviewStrategy(BaseModel):
    """Execution strategy for the new-findings workflow."""

    strategy: ReviewStrategyType
    size_class: PRSizeClass
    max_focus_files: int
    max_prompt_chars: int
    max_comment_entries: int
    suspicious_empty_findings: bool = False
    reason: str = ""


class Finding(BaseModel):
    """Single problem found by AI in targeted code review."""

    severity: FindingSeverity
    category: str
    path: str
    line: Optional[int] = None
    title: str
    why: str
    evidence: str
    snippet: Optional[str] = None
    suggested_comment: str


class ThreadDecision(BaseModel):
    """AI decision on what to do with an existing review thread."""

    thread_id: str
    decision: ThreadDecisionType
    reasoning: str
    suggested_reply: Optional[str] = None
    category: Optional[str] = None
    severity: ThreadSeverity = ThreadSeverity.NONE


class ThreadReviewCandidate(BaseModel):
    """Thread selected for AI analysis in thread-resolution workflow."""

    thread_id: str
    path: Optional[str] = None
    line: Optional[int] = None
    main_comment_body: str
    main_comment_author: str
    replies_count: int = 0
    last_reply_author: Optional[str] = None
    last_reply_body: Optional[str] = None
    is_outdated: bool = False


class ReferencedCommitContext(BaseModel):
    """Remote commit context referenced from a review-thread reply."""

    sha: str
    abbreviated_sha: str
    message: str = ""
    changed_files: list[str] = Field(default_factory=list)
    patch_excerpt: Optional[str] = None


class ThreadReviewContext(BaseModel):
    """Enriched context for AI to decide what to do with a thread."""

    thread_id: str
    comment_id: int
    path: Optional[str] = None
    line: Optional[int] = None
    main_comment_body: str
    main_comment_author: str
    all_replies: list[dict] = Field(default_factory=list)
    current_code_hunk: Optional[str] = None
    referenced_commits: list[ReferencedCommitContext] = Field(default_factory=list)
    is_outdated: bool = False


class ReviewActionProposal(BaseModel):
    """Unified action ready for user review and GitHub submission."""

    action_type: ReviewActionType
    source: ReviewActionSource
    path: Optional[str] = None
    line: Optional[int] = None
    original_line: Optional[int] = None
    resolved_line: Optional[int] = None
    resolution_source: Optional[str] = None
    thread_id: Optional[str] = None
    comment_id: Optional[int] = None
    title: str
    body: str
    reasoning: str
    category: Optional[str] = None
    severity: Optional[FindingSeverity | ThreadSeverity] = None
    anchor_snippet: Optional[str] = None
    evidence: Optional[str] = None
    anchor_confidence: Optional[str] = None
    inline_reason: Optional[str] = None
    why_inline_allowed: Optional[str] = None
    is_inline_safe_for_github: bool = False
    file_status: Optional[str] = None
    is_test_file: bool = False
    read_mode: Optional[str] = None
    related_existing_comment_ids: list[int] = Field(default_factory=list)


class FileContextEntry(BaseModel):
    """Extracted context for one focused file."""

    path: str
    read_mode: Optional[FileReadMode] = None
    full_content: Optional[str] = None
    hunks: list[str] = Field(default_factory=list)
    expanded_hunks: list[str] = Field(default_factory=list)
    worktree_reference: bool = False
    review_hint: str = ""
    changed_hunk_headers: list[str] = Field(default_factory=list)
    approximate_chars: int = 0


class FocusContextBatch(BaseModel):
    """Single bounded batch of review context for one findings prompt."""

    batch_id: str
    files_context: dict[str, FileContextEntry] = Field(default_factory=dict)
    comment_context: list[CommentContextEntry] = Field(default_factory=list)
    checklist_applicable: list[ReviewChecklistItem] = Field(default_factory=list)
    related_files: dict[str, str] = Field(default_factory=dict)
    pr_manifest: Optional[PullRequestManifest] = None
    approximate_chars: int = 0
    prompt_budget_target_chars: int = 0
    prompt_actual_chars: int = 0
    prompt_still_too_large: bool = False
    degraded_context: bool = False


class ReviewContextPackage(BaseModel):
    """Collection of one or more bounded context batches for findings analysis."""

    batches: list[FocusContextBatch] = Field(default_factory=list)


__all__ = [
    "ChangedFileEntry",
    "PullRequestManifest",
    "ChangeManifest",
    "ReviewChecklistItem",
    "ExistingCommentIndexEntry",
    "CommentThreadSummary",
    "CommentContextEntry",
    "ContextRequest",
    "FileReviewPlan",
    "ExcludedFileEntry",
    "ReviewPlan",
    "PRClassification",
    "ScoredReviewCandidate",
    "ReviewStrategy",
    "Finding",
    "ThreadDecision",
    "ThreadReviewCandidate",
    "ThreadReviewContext",
    "ReviewActionProposal",
    "FileContextEntry",
    "FocusContextBatch",
    "ReviewContextPackage",
]
