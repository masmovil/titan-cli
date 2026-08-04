"""Pydantic models for project-specific review profile configuration."""

from pydantic import BaseModel, Field

from .review_enums import ChecklistCategory


class CandidateScoringRule(BaseModel):
    """Rule that adjusts candidate score when path patterns match."""

    name: str = Field(..., description="Stable rule identifier")
    patterns: list[str] = Field(default_factory=list, description="Glob patterns to match")
    score_delta: int = Field(..., description="Positive or negative score adjustment")
    reason: str = Field(..., description="Human-readable rationale added to candidate reasons")


class CandidateExclusions(BaseModel):
    """Configurable low-signal exclusion thresholds."""

    low_signal_test_max_changes: int = Field(default=20)
    low_signal_config_max_changes: int = Field(default=10)


class ReviewAxisRule(BaseModel):
    """Rule that determines when a review axis should apply."""

    always_include: bool = Field(default=False)
    patterns: list[str] = Field(default_factory=list)


class ReviewProfile(BaseModel):
    """Resolved review profile used by deterministic review strategy operations."""

    version: int = Field(default=1)
    change_patterns: dict[str, list[str]] = Field(default_factory=dict)
    file_roles: dict[str, list[str]] = Field(default_factory=dict)
    candidate_scoring: list[CandidateScoringRule] = Field(default_factory=list)
    candidate_exclusions: CandidateExclusions = Field(default_factory=CandidateExclusions)
    review_axes: dict[ChecklistCategory, ReviewAxisRule] = Field(default_factory=dict)
    findings_verification_enabled: bool = Field(
        default=True,
        description="Run the batched refute-or-confirm AI pass over findings before the "
        "human gate. Disable in cost-sensitive projects: it adds one extra AI call per "
        "review when findings exist.",
    )
    findings_batch_concurrency: int = Field(
        default=2,
        ge=1,
        le=4,
        description="How many findings batches run against the CLI at once. Zero token "
        "cost — only wall time. Keep low: each worker is a full CLI session and "
        "provider-side rate limits apply.",
    )
    findings_synthesis_enabled: bool = Field(
        default=False,
        description="Run one extra cross-file synthesis batch (all changed hunks "
        "together, hunks_only) when the PR touches more than one focus file. It "
        "re-sends every hunk already reviewed per-file, so it adds one full AI call "
        "per review; off by default until real cost data justifies it.",
    )


class ReviewChecklistFile(BaseModel):
    """Project-specific checklist file format."""

    version: int = Field(default=1)
    items: list["ReviewChecklistItemFile"] = Field(default_factory=list)


class ReviewChecklistItemFile(BaseModel):
    """Single project-specific review checklist item."""

    id: ChecklistCategory
    name: str
    description: str
    relevant_file_patterns: list[str] = Field(default_factory=list)
