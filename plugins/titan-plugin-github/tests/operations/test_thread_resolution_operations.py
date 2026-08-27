from titan_plugin_github.models.review_models import ReferencedCommitContext, ThreadReviewContext
from titan_plugin_github.models.view import UIComment, UICommentThread
from titan_plugin_github.operations.thread_resolution_operations import (
    batch_thread_review_contexts,
    build_thread_resolution_prompt,
    build_thread_review_candidates,
)


def _make_thread(*, main_author: str, reply_author: str) -> UICommentThread:
    return UICommentThread(
        thread_id=f"thread_{main_author}_{reply_author}",
        main_comment=UIComment(
            id=10,
            body="Please fix this",
            author_login=main_author,
            author_name=main_author,
            formatted_date="",
            path="src/main.py",
            line=42,
        ),
        replies=[
            UIComment(
                id=11,
                body="Fixed",
                author_login=reply_author,
                author_name=reply_author,
                formatted_date="",
                path="src/main.py",
                line=42,
            )
        ],
        is_resolved=False,
        is_outdated=False,
    )


def test_build_thread_review_candidates_only_includes_current_users_threads():
    candidates = build_thread_review_candidates(
        [
            _make_thread(main_author="current-reviewer", reply_author="pr-author"),
            _make_thread(main_author="other-reviewer", reply_author="pr-author"),
        ],
        pr_author="pr-author",
        reviewer_login="current-reviewer",
    )

    assert len(candidates) == 1
    assert candidates[0].main_comment_author == "current-reviewer"


def test_build_thread_review_candidates_excludes_threads_without_pr_author_last_reply():
    candidates = build_thread_review_candidates(
        [_make_thread(main_author="current-reviewer", reply_author="other-reviewer")],
        pr_author="pr-author",
        reviewer_login="current-reviewer",
    )

    assert candidates == []


def test_build_thread_resolution_prompt_includes_referenced_commit_context():
    context = ThreadReviewContext(
        thread_id="thread_123",
        comment_id=10,
        path="src/buttons.kt",
        line=543,
        main_comment_body="Please remove the default dialog state.",
        main_comment_author="reviewer",
        all_replies=[{"author": "author", "body": "Fixed in 343e2e9"}],
        current_code_hunk="@@ -1,2 +1,2 @@\n-old\n+new\n",
        referenced_commits=[
            ReferencedCommitContext(
                sha="343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
                abbreviated_sha="343e2e9",
                message="remove default state value",
                changed_files=["src/BaseDialog.kt"],
                patch_excerpt="diff --git a/src/BaseDialog.kt b/src/BaseDialog.kt\n@@ -1 +1 @@\n-old\n+new\n",
            )
        ],
    )

    prompt = build_thread_resolution_prompt([context])

    assert "Referenced commits from replies" in prompt
    assert "343e2e9" in prompt
    assert "src/BaseDialog.kt" in prompt
    assert "remove default state value" in prompt


def _make_context(thread_id: str, *, body: str = "Please fix this") -> ThreadReviewContext:
    return ThreadReviewContext(
        thread_id=thread_id,
        comment_id=1,
        path="src/main.py",
        line=1,
        main_comment_body=body,
        main_comment_author="reviewer",
        all_replies=[{"author": "author", "body": "Fixed"}],
        current_code_hunk="@@ -1,2 +1,2 @@\n-old\n+new\n",
    )


def test_batch_thread_review_contexts_returns_empty_for_no_contexts():
    assert batch_thread_review_contexts([]) == []


def test_batch_thread_review_contexts_respects_max_threads_per_batch():
    contexts = [_make_context(f"thread_{i}") for i in range(10)]

    batches = batch_thread_review_contexts(
        contexts, max_prompt_chars=1_000_000, max_threads_per_batch=4
    )

    assert [len(batch) for batch in batches] == [4, 4, 2]
    assert sum(len(batch) for batch in batches) == len(contexts)


def test_batch_thread_review_contexts_splits_when_over_char_budget():
    contexts = [_make_context(f"thread_{i}", body="x" * 500) for i in range(4)]

    batches = batch_thread_review_contexts(
        contexts, max_prompt_chars=800, max_threads_per_batch=4
    )

    # Each thread body alone (500 chars) plus prompt scaffolding exceeds the
    # 800-char budget for anything but single-thread batches.
    assert all(len(batch) == 1 for batch in batches)
    assert sum(len(batch) for batch in batches) == len(contexts)


def test_batch_thread_review_contexts_keeps_oversized_single_thread_alone():
    huge_context = _make_context("thread_huge", body="x" * 50_000)

    batches = batch_thread_review_contexts([huge_context], max_prompt_chars=100)

    assert len(batches) == 1
    assert batches[0] == [huge_context]


def test_batch_thread_review_contexts_preserves_full_context_per_thread():
    context = _make_context("thread_1")

    batches = batch_thread_review_contexts([context], max_prompt_chars=1_000_000)

    assert batches == [[context]]
