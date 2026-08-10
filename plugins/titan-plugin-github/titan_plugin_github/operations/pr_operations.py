"""
Pull Request Operations

Pure business logic for PR-related operations.
No UI dependencies - all functions can be unit tested.
"""

import re
from dataclasses import replace
from typing import List
from titan_cli.core.result import ClientSuccess, ClientError
from ..models.view import UICommentThread

# One section of a Titan-generated general review body, as built by
# build_review_action_payload: "**path** (line N):\n<body>" (or "General:" when
# the finding had no path). Sections are joined with "\n\n---\n\n".
_TITAN_BODY_SECTION_RE = re.compile(
    r"^(?:\*\*(?P<path>[^*\n]+)\*\*|General)(?: \(line (?P<line>\d+)\))?:\n(?P<body>.+)$",
    re.DOTALL,
)


def split_titan_review_body(thread: UICommentThread) -> List[UICommentThread]:
    """
    Split a Titan-generated general review body into one pseudo-thread per finding.

    Titan's publish pipeline degrades findings without a valid inline anchor to
    the review's general body, one "**path** (line N):" section per finding. As a
    single blob those findings can't be worked one by one, so this recovers the
    per-finding structure — each part keeps the original author/date and carries
    its own path/line for display and AI context.

    Only bodies where EVERY section matches Titan's exact format are split;
    anything else (human general comments) is returned unchanged as a single
    pseudo-thread.

    Args:
        thread: A general-comment pseudo-thread (is_general_comment=True)

    Returns:
        One pseudo-thread per finding, or [thread] unchanged
    """
    comment = thread.main_comment
    if not thread.is_general_comment or not comment or not comment.body:
        return [thread]

    sections = comment.body.strip().split("\n\n---\n\n")
    matches = [_TITAN_BODY_SECTION_RE.match(s.strip()) for s in sections]
    if not all(matches):
        return [thread]

    parts: List[UICommentThread] = []
    for i, m in enumerate(matches):
        part_comment = replace(
            comment,
            # Negative synthetic id: unique per part for the reply/commit maps,
            # and can never collide with a real (positive) GitHub comment id.
            # General replies go via add_issue_comment, which never uses the id.
            id=-(comment.id * 100 + i),
            body=m.group("body").strip(),
            path=m.group("path"),
            line=int(m.group("line")) if m.group("line") else None,
        )
        parts.append(
            UICommentThread(
                thread_id=f"{thread.thread_id}_f{i}",
                main_comment=part_comment,
                replies=[],
                is_resolved=False,
                is_outdated=False,
            )
        )
    return parts


def build_quote_reply(original_body: str, reply_text: str, max_quote_lines: int = 6) -> str:
    """
    Build a GitHub quote reply: the original comment quoted in markdown, then the
    reply. General PR comments have no thread to reply into, so the quote is what
    ties the new issue comment back to what it answers.

    Args:
        original_body: Body of the comment being answered
        reply_text: The reply itself
        max_quote_lines: Quote at most this many lines of the original

    Returns:
        "> original...\\n\\nreply" markdown text
    """
    lines = [line for line in original_body.strip().splitlines()]
    quoted = [f"> {line}" for line in lines[:max_quote_lines]]
    if len(lines) > max_quote_lines:
        quoted.append("> […]")
    return "\n".join(quoted) + "\n\n" + reply_text.strip()


def fetch_pr_general_comments(
    github_client,
    pr_number: int,
) -> List[UICommentThread]:
    """
    Fetch general PR comments (not attached to code lines), including submitted
    review bodies — where Titan's own unanchorable findings end up.

    Titan-generated review bodies are split into one pseudo-thread per finding
    (see split_titan_review_body); other comments stay whole.

    Filters out:
    - Bot comments
    - Empty comments
    - JSON-only comments (coverage reports, CI badges, etc.)

    Args:
        github_client: GitHub client instance
        pr_number: PR number

    Returns:
        List of UICommentThread pseudo-threads (thread_id starts with "general_")

    Raises:
        Exception: If fetching comments fails
    """
    result = github_client.get_pr_general_comments(pr_number)

    match result:
        case ClientSuccess(data=threads):
            all_threads = threads
        case ClientError(error_message=err):
            raise Exception(f"Failed to fetch general comments: {err}")
        case _:
            raise Exception("Unexpected result type")

    filtered = []
    for thread in all_threads:
        comment = thread.main_comment
        if not comment:
            continue
        if comment.author_login and 'bot' in comment.author_login.lower():
            continue
        if not comment.body or not comment.body.strip():
            continue
        body_stripped = comment.body.strip()
        if body_stripped.startswith('{') and body_stripped.endswith('}'):
            continue
        filtered.extend(split_titan_review_body(thread))

    return filtered


def fetch_pr_threads(
    github_client,
    pr_number: int,
    include_resolved: bool = False
) -> List[UICommentThread]:
    """
    Fetch and filter PR review threads.

    Filters out:
    - Bot comments
    - Empty comments
    - JSON-only comments (coverage reports, etc.)
    - Resolved threads (if include_resolved=False)

    Args:
        github_client: GitHub client instance
        pr_number: PR number
        include_resolved: Whether to include resolved threads

    Returns:
        List of filtered UICommentThread objects (view models)

    Raises:
        Exception: If fetching threads fails
    """
    # Fetch all threads using GraphQL
    result = github_client.get_pr_review_threads(
        pr_number,
        include_resolved=include_resolved
    )

    # Handle ClientResult
    match result:
        case ClientSuccess(data=threads):
            all_threads = threads
        case ClientError(error_message=err):
            raise Exception(f"Failed to fetch threads: {err}")
        case _:
            raise Exception("Unexpected result type")

    # Filter out unwanted threads
    filtered_threads = []

    for thread in all_threads:
        main_comment = thread.main_comment
        if not main_comment:
            continue

        # Skip bot comments
        if main_comment.author_login and 'bot' in main_comment.author_login.lower():
            continue

        # Skip empty comments
        if not main_comment.body or not main_comment.body.strip():
            continue

        # Skip JSON-only comments (coverage reports, etc.)
        body_stripped = main_comment.body.strip()
        if body_stripped.startswith('{') and body_stripped.endswith('}'):
            continue

        filtered_threads.append(thread)

    return filtered_threads
