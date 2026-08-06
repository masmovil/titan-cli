"""
Commit Operations

Pure business logic for commit message handling.
These functions can be used by any step and are easily testable.
"""

from typing import Optional, Tuple

from titan_cli.core.diffs import (
    SAMPLED_DIFF_NOTE,
    budget_diff_across_files,
    format_file_summary,
)


def build_ai_commit_prompt(diff_text: str, files_list: list, max_diff_chars: int = 8000) -> str:
    """
    Build the AI prompt for generating a commit message.

    The prompt always carries a complete per-file summary, even when the diff itself has to
    be cut: the message has to describe the whole commit, and it can only weigh what it was
    shown.

    Args:
        diff_text: Full git diff output
        files_list: List of changed file paths
        max_diff_chars: Character budget for the diff body, shared across files

    Returns:
        Complete prompt string for AI
    """
    # One file list, not two: the per-file counts carry the same paths and say how much each
    # one changed. Listing them twice doubled the part of the prompt that grows with the size
    # of the commit, for no extra information.
    stat_summary = format_file_summary(diff_text)
    if not stat_summary:
        stat_summary = (
            "\n".join(f"  - {f}" for f in files_list) if files_list else "(checking diff)"
        )

    diff_preview = budget_diff_across_files(diff_text, max_diff_chars)
    truncated = len(diff_preview) < len(diff_text)

    prompt = f"""Analyze these code changes and generate a conventional commit message.

## Changed files ({len(files_list)} total), with lines added and removed
{stat_summary}

## Diff
{SAMPLED_DIFF_NOTE if truncated else ""}
```diff
{diff_preview}
```

## CRITICAL Instructions
Generate ONE single-line conventional commit message following this EXACT format:
- type: Description
- Types: feat, fix, refactor, docs, test, chore, style, perf
- Description: clear summary in imperative mood, starting with CAPITAL letter (be descriptive, concise, and at least 5 words long)
- NO line breaks, NO body, NO additional explanation

The single line must summarise the WHOLE commit as well as one line can:
- Describe the overall change, not the first detail you happened to read
- When the commit spans several areas, name the change that ties them together rather than
  picking one file's story - a message that describes a fraction of the commit is wrong even
  when the fraction is accurate
- Prefer the production behaviour that changed over the tests that came with it
- Choose the type that fits the main change, not the largest number of lines

Examples (notice they start with capital letter and are all one line):
- feat: Add OAuth2 integration with Google provider
- fix: Resolve race condition in cache invalidation
- refactor: Simplify menu component and remove unused props
- refactor: Add support for nested workflow execution

Return ONLY the single-line commit message, absolutely nothing else."""

    return prompt


def normalize_commit_message(raw_message: str) -> str:
    """
    Normalize a commit message by removing quotes, extra whitespace, and taking first line.

    Args:
        raw_message: Raw commit message from AI or user input

    Returns:
        Normalized single-line commit message

    Examples:
        >>> normalize_commit_message('"feat: Add feature"')
        'feat: Add feature'
        >>> normalize_commit_message("'fix: Bug fix'")
        'fix: Bug fix'
        >>> normalize_commit_message("  feat: Feature  \\n\\nBody text")
        'feat: Feature'
        >>> normalize_commit_message('  "feat: Feature"  ')
        'feat: Feature'
    """
    # Strip whitespace
    message = raw_message.strip()

    # Take only first line
    message = message.split('\n')[0].strip()

    # Remove surrounding quotes
    message = message.strip('"').strip("'").strip()

    return message


def capitalize_commit_subject(commit_message: str) -> str:
    """
    Capitalize the subject part of a conventional commit message.

    Format: "type: Subject" → "type: Subject" (with capital S)

    Args:
        commit_message: Commit message in conventional format

    Returns:
        Commit message with capitalized subject

    Examples:
        >>> capitalize_commit_subject("feat: add new feature")
        'feat: Add new feature'
        >>> capitalize_commit_subject("fix: resolve bug")
        'fix: Resolve bug'
        >>> capitalize_commit_subject("no colon here")
        'no colon here'
        >>> capitalize_commit_subject("feat: Already Capitalized")
        'feat: Already Capitalized'
    """
    if ':' not in commit_message:
        return commit_message

    parts = commit_message.split(':', 1)
    if len(parts) != 2:
        return commit_message

    prefix = parts[0]  # type
    subject = parts[1].strip()  # description

    # Capitalize first letter of subject if it's lowercase
    if subject and subject[0].islower():
        subject = subject[0].upper() + subject[1:]

    return f"{prefix}: {subject}"


def validate_message_length(message: str, max_length: int = 72) -> Tuple[bool, Optional[int]]:
    """
    Validate commit message length.

    Args:
        message: Commit message to validate
        max_length: Maximum recommended length (default: 72)

    Returns:
        Tuple of (is_valid, actual_length) where:
        - is_valid: True if length <= max_length
        - actual_length: The actual message length

    Examples:
        >>> validate_message_length("Short message")
        (True, 13)
        >>> validate_message_length("a" * 80, max_length=72)
        (False, 80)
        >>> validate_message_length("Exactly 72 chars" + "a" * 56, max_length=72)
        (True, 72)
    """
    length = len(message)
    is_valid = length <= max_length
    return is_valid, length


def process_ai_commit_message(raw_ai_response: str) -> str:
    """
    Complete processing pipeline for AI-generated commit messages.

    Combines normalization and capitalization.

    Args:
        raw_ai_response: Raw response from AI

    Returns:
        Processed commit message ready to use

    Examples:
        >>> process_ai_commit_message('"feat: add new feature"')
        'feat: Add new feature'
        >>> process_ai_commit_message("  'fix: resolve bug'  \\n\\nExtra text")
        'fix: Resolve bug'
    """
    normalized = normalize_commit_message(raw_ai_response)
    capitalized = capitalize_commit_subject(normalized)
    return capitalized


__all__ = [
    "build_ai_commit_prompt",
    "normalize_commit_message",
    "capitalize_commit_subject",
    "validate_message_length",
    "process_ai_commit_message",
]
