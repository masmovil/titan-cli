from titan_plugin_github.models.review_enums import CommentContextKind, FileChangeStatus
from titan_plugin_github.models.view import UIComment, UICommentThread, UIFileChange
from titan_plugin_github.models.review_models import ExistingCommentIndexEntry, Finding
from titan_plugin_github.models.review_enums import FindingSeverity
from titan_plugin_github.models.validators import is_duplicate
from titan_plugin_github.models.review_profile_models import CandidateExclusions, ReviewProfile
from titan_plugin_github.operations.manifest_operations import (
    build_change_manifest,
    build_comment_review_context,
    build_existing_comments_index,
    is_test_file,
)


def test_build_change_manifest_sets_generic_flags(sample_ui_pr):
    files = [
        UIFileChange(
            path="android/app/build.gradle.kts",
            additions=4,
            deletions=1,
            status=FileChangeStatus.MODIFIED,
            status_icon="~",
        ),
        UIFileChange(
            path="ios/Podfile.lock",
            additions=8,
            deletions=2,
            status=FileChangeStatus.MODIFIED,
            status_icon="~",
        ),
        UIFileChange(
            path="docs/architecture.md",
            additions=12,
            deletions=0,
            status=FileChangeStatus.MODIFIED,
            status_icon="~",
        ),
    ]

    manifest = build_change_manifest(sample_ui_pr, files)

    assert manifest.files[0].is_config is True
    assert manifest.files[1].is_lockfile is True
    assert manifest.files[2].is_docs is True


def test_is_test_file_covers_multi_language_conventions():
    test_paths = [
        "app/src/test/kotlin/com/foo/FooViewModelTest.kt",
        "app/src/androidTest/kotlin/com/foo/FooScreenTest.kt",
        "src/main/java/com/foo/FooServiceTests.java",
        "Sources/FooTests/FooTest.swift",
        "pkg/server/handler_test.go",
        "src/FooSpec.scala",
        "tests/test_api.py",
        "src/components/Button.test.tsx",
    ]
    for path in test_paths:
        assert is_test_file(path), path


def test_is_test_file_does_not_claim_production_lookalikes():
    production_paths = [
        "src/latest.py",
        "app/contest/views.py",
        "lib/attestation.py",
        "src/protest_handler.py",
        "app/src/main/kotlin/com/foo/Latest.kt",
        "src/detestable_module.py",
    ]
    for path in production_paths:
        assert not is_test_file(path), path


def test_is_test_file_uses_profile_declared_globs():
    profile = ReviewProfile(
        version=1,
        change_patterns={},
        file_roles={"tests": ["**/*Fixtures.kt", "sharedTest/src/main/kotlin/**"]},
        candidate_scoring=[],
        candidate_exclusions=CandidateExclusions(),
        review_axes={},
    )

    assert is_test_file("app/src/test/kotlin/FooFixtures.kt", profile)
    assert is_test_file("sharedTest/src/main/kotlin/com/foo/Helper.kt", profile)
    # Without the profile, only built-in conventions apply.
    assert not is_test_file("app/src/foo/FooFixtures.kt")


def test_build_change_manifest_marks_tests_via_profile(sample_ui_pr):
    profile = ReviewProfile(
        version=1,
        change_patterns={},
        file_roles={"tests": ["**/*Fixtures.kt"]},
        candidate_scoring=[],
        candidate_exclusions=CandidateExclusions(),
        review_axes={},
    )
    files = [
        UIFileChange(
            path="app/src/foo/FooFixtures.kt",
            additions=30,
            deletions=0,
            status=FileChangeStatus.ADDED,
            status_icon="+",
        ),
    ]

    without_profile = build_change_manifest(sample_ui_pr, files)
    with_profile = build_change_manifest(sample_ui_pr, files, profile)

    assert without_profile.files[0].is_test is False
    assert with_profile.files[0].is_test is True


def test_build_change_manifest_uses_local_churn_for_zeroed_counters(sample_ui_pr):
    """GitHub reports 0/0 for files whose diff it cannot render; the local numstat
    counters must take over exactly there — never on files with real API counters
    and never on pure renames (0/0 IS their real churn)."""
    files = [
        UIFileChange(
            path="src/huge_generated_client.py",
            additions=0,
            deletions=0,
            status=FileChangeStatus.ADDED,
            status_icon="+",
        ),
        UIFileChange(
            path="src/normal.py",
            additions=10,
            deletions=2,
            status=FileChangeStatus.MODIFIED,
            status_icon="~",
        ),
        UIFileChange(
            path="src/renamed.py",
            additions=0,
            deletions=0,
            status=FileChangeStatus.RENAMED,
            status_icon="→",
        ),
    ]
    churn = {
        "src/huge_generated_client.py": (1500, 0),
        "src/normal.py": (11, 3),
        "src/renamed.py": (200, 0),
    }

    manifest = build_change_manifest(sample_ui_pr, files, churn_by_path=churn)

    by_path = {entry.path: entry for entry in manifest.files}
    assert by_path["src/huge_generated_client.py"].additions == 1500
    assert by_path["src/normal.py"].additions == 10  # API counters win when present
    assert by_path["src/renamed.py"].additions == 0  # pure rename untouched
    assert manifest.total_additions == 1500 + 10 + 0


def test_build_comment_review_context_summarizes_long_threads():
    main = UIComment(
        id=1,
        body="There is no validation when parsing the payload and this can crash on null input.",
        author_login="reviewer",
        author_name="Reviewer",
        formatted_date="2026-01-01",
        path="src/api.py",
        line=10,
    )
    reply = UIComment(
        id=2,
        body="I added a guard for null payloads and a regression test in the latest commit.",
        author_login="author",
        author_name="Author",
        formatted_date="2026-01-02",
        path="src/api.py",
        line=10,
    )
    thread = UICommentThread(
        thread_id="t1",
        main_comment=main,
        replies=[reply],
        is_resolved=False,
        is_outdated=False,
    )

    context = build_comment_review_context([thread], [], max_entries=5, max_chars=1000)

    assert len(context) == 1
    assert context[0].kind == CommentContextKind.THREAD_SUMMARY
    assert "Latest reply" in context[0].summary


def test_build_comment_review_context_filters_bot_comments():
    bot_comment = UIComment(
        id=3,
        body="Automated report.",
        author_login="danger[bot]",
        author_name="Danger",
        formatted_date="2026-01-03",
        path=None,
        line=None,
    )
    thread = UICommentThread(
        thread_id="general_3",
        main_comment=bot_comment,
        replies=[],
        is_resolved=False,
        is_outdated=False,
    )

    context = build_comment_review_context([], [thread], max_entries=5, max_chars=1000)

    assert context == []


def test_build_comment_review_context_filters_wiz_html_comments():
    bot_like_comment = UIComment(
        id=4,
        body='<a><picture><source media="(prefers-color-scheme: dark)" srcset="https://assets.wiz.io/wiz-code/long_severity_tags/low_dark.svg"></picture></a>',
        author_login="security-scanner",
        author_name="Scanner",
        formatted_date="2026-01-03",
        path=None,
        line=None,
    )
    thread = UICommentThread(
        thread_id="general_4",
        main_comment=bot_like_comment,
        replies=[],
        is_resolved=False,
        is_outdated=False,
    )

    context = build_comment_review_context([], [thread], max_entries=5, max_chars=1000)

    assert context == []


def test_build_comment_review_context_skips_adjudicated_resolved_threads():
    main = UIComment(
        id=10,
        body="This change may lose non-string analytics values.",
        author_login="reviewer",
        author_name="Reviewer",
        formatted_date="2026-01-01",
        path="src/api.py",
        line=10,
    )
    reply = UIComment(
        id=11,
        body="Everything here is stringly typed by design.",
        author_login="author",
        author_name="Author",
        formatted_date="2026-01-02",
        path="src/api.py",
        line=10,
    )
    thread = UICommentThread(
        thread_id="t2",
        main_comment=main,
        replies=[reply],
        is_resolved=True,
        is_outdated=False,
    )

    context = build_comment_review_context([thread], [], max_entries=5, max_chars=1000)
    index = build_existing_comments_index([thread], [])

    assert context == []
    assert index[0].is_adjudicated is True
    assert index[0].has_author_reply is True


def test_build_comment_review_context_filters_non_bug_like_review_comments():
    design_comment = UIComment(
        id=12,
        body="One suggestion regarding this: this is going to be a bit of a pain if we keep adding events here.",
        author_login="reviewer",
        author_name="Reviewer",
        formatted_date="2026-01-01",
        path="src/api.py",
        line=20,
    )
    thread = UICommentThread(
        thread_id="t4",
        main_comment=design_comment,
        replies=[],
        is_resolved=False,
        is_outdated=False,
    )

    context = build_comment_review_context([thread], [], max_entries=5, max_chars=1000)
    index = build_existing_comments_index([thread], [])

    assert context == []
    assert len(index) == 1


def test_build_comment_review_context_keeps_bug_like_comments():
    bug_comment = UIComment(
        id=13,
        body="This branch maps view_item to select_item, so the tracker UI will show the wrong event type.",
        author_login="reviewer",
        author_name="Reviewer",
        formatted_date="2026-01-01",
        path="src/api.py",
        line=30,
    )
    thread = UICommentThread(
        thread_id="t5",
        main_comment=bug_comment,
        replies=[],
        is_resolved=False,
        is_outdated=False,
    )

    context = build_comment_review_context([thread], [], max_entries=5, max_chars=1000)

    assert len(context) == 1
    assert context[0].path == "src/api.py"


def test_is_duplicate_matches_adjudicated_resolved_thread_when_titles_are_similar():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="functional_correctness",
        path="src/api.py",
        line=10,
        title="Serializer drops non-string analytics values",
        why="Why",
        evidence="bundle.getString(k)",
        suggested_comment="Comment",
    )
    existing = ExistingCommentIndexEntry(
        comment_id=1,
        thread_id="t3",
        is_resolved=True,
        path="src/api.py",
        line=10,
        category="functional_correctness",
        title="This change may lose non-string analytics values",
        author="reviewer",
        has_author_reply=True,
        last_reply_author="author",
        reply_count=1,
        is_adjudicated=True,
    )

    assert is_duplicate(finding, existing) is True


def test_is_duplicate_does_not_suppress_different_adjudicated_issue_same_category():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="performance",
        path="src/api.py",
        line=10,
        title="Repeated JSON parsing inside render loop",
        why="Why",
        evidence="parseJson() in loop",
        suggested_comment="Comment",
    )
    existing = ExistingCommentIndexEntry(
        comment_id=1,
        thread_id="t3",
        is_resolved=True,
        path="src/api.py",
        line=10,
        category="performance",
        title="Rename temporary variable for clarity",
        author="reviewer",
        has_author_reply=True,
        last_reply_author="author",
        reply_count=1,
        is_adjudicated=True,
    )

    assert is_duplicate(finding, existing) is False


def test_is_duplicate_returns_false_for_different_paths():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="functional_correctness",
        path="src/api.py",
        line=10,
        title="Serializer drops non-string analytics values",
        why="Why",
        evidence="bundle.getString(k)",
        suggested_comment="Comment",
    )
    existing = ExistingCommentIndexEntry(
        comment_id=1,
        thread_id="t3",
        is_resolved=True,
        path="src/different_api.py",
        line=10,
        category="functional_correctness",
        title="This change may lose non-string analytics values",
        author="reviewer",
        has_author_reply=True,
        last_reply_author="author",
        reply_count=1,
        is_adjudicated=True,
    )

    assert is_duplicate(finding, existing) is False


def test_is_duplicate_returns_false_for_different_lines():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="functional_correctness",
        path="src/api.py",
        line=10,
        title="Serializer drops non-string analytics values",
        why="Why",
        evidence="bundle.getString(k)",
        suggested_comment="Comment",
    )
    existing = ExistingCommentIndexEntry(
        comment_id=1,
        thread_id="t3",
        is_resolved=True,
        path="src/api.py",
        line=20,
        category="functional_correctness",
        title="This change may lose non-string analytics values",
        author="reviewer",
        has_author_reply=True,
        last_reply_author="author",
        reply_count=1,
        is_adjudicated=True,
    )

    assert is_duplicate(finding, existing) is False


def test_is_duplicate_returns_false_if_not_adjudicated_and_dissimilar():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="functional_correctness",
        path="src/api.py",
        line=10,
        title="Serializer drops non-string analytics values",
        why="Why",
        evidence="bundle.getString(k)",
        suggested_comment="Comment",
    )
    existing = ExistingCommentIndexEntry(
        comment_id=1,
        thread_id="t3",
        is_resolved=True,
        path="src/api.py",
        line=10,
        category="functional_correctness",
        title="Completely different title",
        author="reviewer",
        has_author_reply=True,
        last_reply_author="author",
        reply_count=1,
        is_adjudicated=False,
    )

    assert is_duplicate(finding, existing, title_similarity_threshold=0.9) is False
