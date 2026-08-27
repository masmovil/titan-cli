"""Operations for building PR selection option content."""

from titan_plugin_github.models.view import UIPullRequest


def escape_rich_markup(text: str) -> str:
    """Escape square brackets in user-controlled text for Rich markup rendering."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def format_review_status_badge(review_status_summary: str) -> str:
    """Format a compact inline badge for PR review status."""
    badges = {
        "approved": "[green]● approved[/green]",
        "changes requested": "[red]● changes requested[/red]",
        "draft": "[yellow]● draft[/yellow]",
        "review required": "[blue]● review required[/blue]",
        "ready for review": "[cyan]● ready for review[/cyan]",
    }
    return badges.get(review_status_summary, escape_rich_markup(review_status_summary))


def build_pr_selection_title(
    pr: UIPullRequest,
    highlight_assigned: bool = False,
    include_review_badge: bool = False,
) -> str:
    """Build the title for a PR selection option."""
    prefix = "⭐ " if highlight_assigned else ""
    title = f"{prefix}#{pr.number}: {escape_rich_markup(pr.title)}"

    if include_review_badge and pr.review_status_summary:
        return f"{title}  {format_review_status_badge(pr.review_status_summary)}"

    return title


def build_pr_selection_description(
    pr: UIPullRequest,
    *,
    include_author: bool = False,
    include_checks: bool = False,
    include_review_status: bool = False,
) -> str:
    """Build the description for a PR selection option."""
    parts: list[str] = []

    if include_author:
        parts.append(f"by {pr.author_name}")

    parts.append(pr.branch_info)

    if include_checks and pr.checks_summary:
        parts.append(f"Checks: {pr.checks_summary}")

    if include_review_status and pr.review_status_summary:
        parts.append(f"Review: {pr.review_status_summary}")

    return " · ".join(parts)
