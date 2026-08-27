"""Operations for building cheap PR context and compact comments context."""

import re
from pathlib import Path
from typing import Optional

from ..models.review_enums import CommentContextKind
from ..models.review_models import (
    ChangeManifest,
    ChangedFileEntry,
    CommentContextEntry,
    ExistingCommentIndexEntry,
    PullRequestManifest,
)
from ..models.review_profile_models import ReviewProfile
from ..models.view import UICommentThread, UIFileChange, UIPullRequest
from .review_profile_operations import path_matches_any


_TEST_PATH_PATTERNS = [
    r"(^|/)tests?/",
    r"(^|/)[a-z]+Tests?/",
    r"(^|/)test_",
    r"_test\.py$",
    r"_spec\.py$",
    r"(^|/)spec/",
    r"\.test\.[jt]sx?$",
    r"\.spec\.[jt]sx?$",
    r"_test\.go$",
    r"Tests?\.(kt|java|cs|swift|scala)$",
    r"Spec\.(kt|scala|groovy)$",
]
_DOC_PATH_PATTERNS = [r"(^|/)docs?/", r"\.md$", r"\.rst$", r"\.adoc$"]
_GENERATED_PATH_PATTERNS = [r"(^|/)dist/", r"(^|/)build/", r"(^|/)vendor/", r"(^|/)generated/"]
_CONFIG_SUFFIXES = {
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".json",
    ".gradle",
    ".kts",
    ".plist",
    ".pbxproj",
}
_LOCKFILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "pdm.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "podfile.lock",
    "packages.resolved",
    "package.resolved",
    "paket.lock",
    "pubspec.lock",
}

_TEST_REGEXES = [re.compile(p) for p in _TEST_PATH_PATTERNS]
_DOC_REGEXES = [re.compile(p) for p in _DOC_PATH_PATTERNS]
_GENERATED_REGEXES = [re.compile(p) for p in _GENERATED_PATH_PATTERNS]


def is_test_file(path: str, review_profile: Optional[ReviewProfile] = None) -> bool:
    """Detect test files, preferring the project's own declared test globs.

    Built-in patterns only cover a handful of language conventions, so a project that
    declares ``file_roles.tests`` knows better than they do. The union is intentional:
    the profile adds its conventions without having to restate the built-in ones.
    """
    if any(rx.search(path) for rx in _TEST_REGEXES):
        return True
    if review_profile is None:
        return False
    return path_matches_any(path, review_profile.file_roles.get("tests", []))


def is_docs_file(path: str) -> bool:
    return any(rx.search(path) for rx in _DOC_REGEXES)


def is_generated_file(path: str) -> bool:
    return any(rx.search(path) for rx in _GENERATED_REGEXES)


def is_config_file(path: str) -> bool:
    p = Path(path)
    name = p.name.lower()
    return (
        p.suffix.lower() in _CONFIG_SUFFIXES
        or p.name.startswith(".")
        or name.startswith(("dockerfile", "makefile", "podfile", "fastfile"))
        or name.endswith((".gradle.kts", ".xcconfig"))
    )


def is_lockfile(path: str) -> bool:
    return Path(path).name.lower() in _LOCKFILE_NAMES


def is_rename_only(file_change: UIFileChange) -> bool:
    return file_change.status.value == "renamed" and file_change.additions == 0 and file_change.deletions == 0


def build_change_manifest(
    pr: UIPullRequest,
    files: list[UIFileChange],
    review_profile: Optional[ReviewProfile] = None,
    churn_by_path: Optional[dict[str, tuple[int, int]]] = None,
) -> ChangeManifest:
    """Build the typed manifest of a PR's changed files.

    ``churn_by_path`` maps path -> (additions, deletions) from a local git numstat.
    GitHub's files API reports 0/0 for files whose diff it cannot render (too
    large or binary); a zero entry here would score as "nothing changed", so the
    local counters take over exactly in that case and only in that case.
    """
    churn_by_path = churn_by_path or {}
    entries: list[ChangedFileEntry] = []
    for f in files:
        additions, deletions = f.additions, f.deletions
        # A pure rename also reports 0/0, but that IS the real churn — and the
        # numstat source uses --no-renames, which would report the new path as a
        # full-file addition. Never override renames.
        if additions == 0 and deletions == 0 and not is_rename_only(f) and f.path in churn_by_path:
            additions, deletions = churn_by_path[f.path]
        entries.append(
            ChangedFileEntry(
                path=f.path,
                status=f.status,
                additions=additions,
                deletions=deletions,
                is_test=is_test_file(f.path, review_profile),
                size_lines=0,
                is_docs=is_docs_file(f.path),
                is_generated=is_generated_file(f.path),
                is_config=is_config_file(f.path),
                is_lockfile=is_lockfile(f.path),
                is_rename_only=is_rename_only(f),
            )
        )

    pr_manifest = PullRequestManifest(
        number=pr.number,
        title=pr.title,
        base=pr.base_ref,
        head=pr.head_ref,
        author=pr.author_name,
        description=pr.body or "",
    )

    return ChangeManifest(
        pr=pr_manifest,
        files=entries,
        total_additions=sum(entry.additions for entry in entries),
        total_deletions=sum(entry.deletions for entry in entries),
    )


def _infer_category(body: str) -> Optional[str]:
    lower = body.lower()
    if any(k in lower for k in ("test", "coverage", "mock", "assert")):
        return "test_coverage"
    if any(k in lower for k in ("except", "error", "exception", "raise", "catch", "handle")):
        return "error_handling"
    if any(k in lower for k in ("security", "inject", "xss", "sql", "auth", "token", "secret")):
        return "security"
    if any(k in lower for k in ("performance", "slow", "n+1", "cache", "latency", "timeout")):
        return "performance"
    if any(k in lower for k in ("api", "contract", "schema", "interface", "endpoint")):
        return "api_contract"
    if any(k in lower for k in ("concurren", "thread", "async", "lock", "race")):
        return "concurrency"
    if any(k in lower for k in ("logic", "bug", "incorrect", "wrong", "broken")):
        return "functional_correctness"
    if any(k in lower for k in ("validate", "validation", "sanitize", "nullable", "none")):
        return "data_validation"
    return None


def _looks_like_automated_comment(author_login: str, body: str) -> bool:
    lower_author = (author_login or "").lower()
    lower_body = body.lower()
    if any(token in lower_author for token in ("[bot]", "bot", "danger", "codecov", "sonar", "copilot")):
        return True
    if lower_body.startswith("<!--"):
        return True
    if any(token in lower_body for token in ("<table", "<picture", "<source", "<img", "</table>", "</picture>")):
        return True
    if any(
        token in lower_body
        for token in (
            "warnings:",
            "markdowns -->",
            "coverage report",
            "generated by danger",
            "wiz.io",
            "assets.wiz.io",
            "severity_tags",
            "security issues found",
            "vulnerability",
        )
    ):
        return True
    return False


def _has_author_reply(thread: UICommentThread) -> bool:
    main_author = (thread.main_comment.author_login or "").lower()
    return any((reply.author_login or "").lower() != main_author for reply in thread.replies)


def _last_reply_author(thread: UICommentThread) -> Optional[str]:
    if not thread.replies:
        return None
    return thread.replies[-1].author_login


def _is_adjudicated_thread(thread: UICommentThread) -> bool:
    return thread.is_resolved and _has_author_reply(thread)


def _looks_like_bug_or_risk_comment(body: str) -> bool:
    lower = body.lower()
    strong_positive_signals = (
        "bug",
        "break",
        "breaks",
        "incorrect",
        "wrong",
        "fail",
        "fails",
        "crash",
        "risk",
        "null",
        "error",
        "missing",
        "drop",
        "lose",
        "block",
        "regression",
        "does not",
        "won't",
        "runtime",
        "throws",
        "throw",
        "silently",
        "mislabeled",
        "null/missing",
    )
    negative_signals = (
        "rename",
        "naming",
        "hardcoded string",
        "nit",
        "style",
        "freyja",
        "question here",
        "up to discussion",
        "do we need to indent",
        "move this logic",
        "should we use",
        "one suggestion",
        "may be able to",
        "pain if we keep",
        "painful if we keep",
        "do we want to expose",
        "specific to the analytics tracker",
        "private fun",
        "maintainability",
        "cleaner",
        "maybe always",
        "maybe we should",
    )
    if any(token in lower for token in negative_signals):
        return False
    if any(token in lower for token in strong_positive_signals):
        return True

    category = _infer_category(body)
    if category in {"functional_correctness", "error_handling", "data_validation", "security"}:
        return any(
            token in lower
            for token in (
                " if ",
                " when ",
                "value",
                "mapped",
                "recorded",
                "serialize",
                "convert",
                "return",
            )
        )
    return False


def build_existing_comments_index(
    review_threads: list[UICommentThread],
    general_comments: list[UICommentThread],
) -> list[ExistingCommentIndexEntry]:
    index: list[ExistingCommentIndexEntry] = []

    for thread in review_threads:
        mc = thread.main_comment
        if _looks_like_automated_comment(mc.author_login, mc.body):
            continue
        index.append(
            ExistingCommentIndexEntry(
                comment_id=mc.id,
                thread_id=thread.thread_id,
                is_resolved=thread.is_resolved,
                path=mc.path,
                line=mc.line,
                category=_infer_category(mc.body),
                title=mc.body[:80].strip(),
                author=mc.author_login,
                has_author_reply=_has_author_reply(thread),
                last_reply_author=_last_reply_author(thread),
                reply_count=len(thread.replies),
                is_adjudicated=_is_adjudicated_thread(thread),
            )
        )
        for reply in thread.replies:
            if _looks_like_automated_comment(reply.author_login, reply.body):
                continue
            index.append(
                ExistingCommentIndexEntry(
                    comment_id=reply.id,
                    thread_id=thread.thread_id,
                    is_resolved=thread.is_resolved,
                    path=reply.path or mc.path,
                    line=reply.line or mc.line,
                    category=_infer_category(reply.body),
                    title=reply.body[:80].strip(),
                    author=reply.author_login,
                    has_author_reply=_has_author_reply(thread),
                    last_reply_author=_last_reply_author(thread),
                    reply_count=len(thread.replies),
                    is_adjudicated=_is_adjudicated_thread(thread),
                )
            )

    for gc in general_comments:
        mc = gc.main_comment
        if _looks_like_automated_comment(mc.author_login, mc.body):
            continue
        index.append(
            ExistingCommentIndexEntry(
                comment_id=mc.id,
                thread_id=gc.thread_id,
                is_resolved=gc.is_resolved,
                path=None,
                line=None,
                category=_infer_category(mc.body),
                title=mc.body[:80].strip(),
                author=mc.author_login,
                has_author_reply=_has_author_reply(gc),
                last_reply_author=_last_reply_author(gc),
                reply_count=len(gc.replies),
                is_adjudicated=_is_adjudicated_thread(gc),
            )
        )

    return index


def build_comment_review_context(
    review_threads: list[UICommentThread],
    general_comments: list[UICommentThread],
    max_entries: int = 12,
    max_chars: int = 2400,
    include_resolved: bool = False,
    bug_risk_only: bool = True,
) -> list[CommentContextEntry]:
    """Build prompt-friendly comment context with thread summaries when needed."""

    def make_thread_entry(thread: UICommentThread) -> CommentContextEntry:
        main = thread.main_comment
        if thread.replies:
            latest = thread.replies[-1]
            latest_state = latest.body.strip().replace("\n", " ")[:180]
            summary = (
                f"Initial: {main.body.strip().replace(chr(10), ' ')[:180]}. "
                f"Latest reply by @{latest.author_login}: {latest_state}"
            )
            kind = CommentContextKind.THREAD_SUMMARY
        else:
            summary = main.body.strip().replace("\n", " ")[:220]
            kind = CommentContextKind.COMMENT
        return CommentContextEntry(
            kind=kind,
            thread_id=thread.thread_id,
            path=main.path,
            line=main.line,
            category=_infer_category(main.body),
            title=main.body[:80].strip(),
            summary=summary,
            is_resolved=thread.is_resolved,
            has_author_reply=_has_author_reply(thread),
            last_reply_author=_last_reply_author(thread),
            reply_count=len(thread.replies),
            is_adjudicated=_is_adjudicated_thread(thread),
        )

    def include_thread(thread: UICommentThread) -> bool:
        main = thread.main_comment
        if _looks_like_automated_comment(main.author_login, main.body):
            return False
        if not include_resolved and thread.is_resolved:
            return False
        if bug_risk_only and not _looks_like_bug_or_risk_comment(main.body):
            return False
        if _is_adjudicated_thread(thread):
            return False
        return True

    prioritized_threads = sorted(
        [thread for thread in review_threads if include_thread(thread)],
        key=lambda t: (
            t.is_resolved,
            not _looks_like_bug_or_risk_comment(t.main_comment.body),
            t.is_general_comment,
            0 if t.main_comment.path else 1,
            -len(t.replies),
        ),
    )
    entries = [make_thread_entry(thread) for thread in prioritized_threads]

    for general in general_comments:
        main = general.main_comment
        if _looks_like_automated_comment(main.author_login, main.body):
            continue
        if not include_resolved and general.is_resolved:
            continue
        if bug_risk_only and not _looks_like_bug_or_risk_comment(main.body):
            continue
        if _is_adjudicated_thread(general):
            continue
        entries.append(
            CommentContextEntry(
                kind=CommentContextKind.COMMENT,
                thread_id=general.thread_id,
                path=None,
                line=None,
                category=_infer_category(main.body),
                title=main.body[:80].strip(),
                summary=main.body.strip().replace("\n", " ")[:220],
                is_resolved=general.is_resolved,
                has_author_reply=_has_author_reply(general),
                last_reply_author=_last_reply_author(general),
                reply_count=len(general.replies),
                is_adjudicated=_is_adjudicated_thread(general),
            )
        )

    result: list[CommentContextEntry] = []
    used_chars = 0
    for entry in entries:
        if len(result) >= max_entries:
            break
        entry_size = len(entry.title) + len(entry.summary)
        if result and used_chars + entry_size > max_chars:
            break
        result.append(entry)
        used_chars += entry_size

    return result
